import pomice
import random

from typing import Coroutine, Any
from contextlib import suppress

from discord import Embed, Message, HTTPException, Member, VoiceState, utils
from discord.ext.commands import Cog, command

from tools.helpers import PretendContext
from tools.converters import EligibleVolume
from tools.predicates import is_voice, bot_is_voice


class Player(pomice.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = pomice.Queue()
        self.ctx: PretendContext = None
        self.loop: bool = False
        self.current_track: pomice.Track = None
        self.awaiting = False

    def shuffle(self) -> None:
        return random.shuffle(self.queue)

    async def set_pause(self, pause: bool) -> Coroutine[Any, Any, bool]:
        if pause is True:
            self.awaiting = True
        else:
            if self.awaiting:
                self.awaiting = False

        return await super().set_pause(pause)

    async def do_next(self, track: pomice.Track = None) -> None:
        if not self.loop:
            if not track:
                try:
                    track: pomice.Track = self.queue.get()
                except pomice.QueueEmpty:
                    return await self.kill()

            self.current_track = track

        await self.play(self.current_track)
        await self.channel.edit(status=f"Playing: {track.title}")
        await self.context.send(
            embed=Embed(
                color=self.context.bot.color,
                description=f"🎵 {self.context.author.mention}: Now playing [**{track.title}**]({track.uri})",
            )
        )

        if self.awaiting:
            self.awaiting = False

    def set_context(self, ctx: PretendContext):
        self.context = ctx

    async def kill(self) -> Message:
        with suppress((HTTPException), (KeyError)):
            await self.destroy()
            return await self.context.send_success("Left the voice channel")


class Music(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emoji = "🎵"
        self.pomice = pomice.NodePool()
        self.description = "Music commands"

    async def music_send(self, ctx: PretendContext, message: str) -> Message:
        """
        send a music themed message
        """

        embed = Embed(
            color=self.bot.color, description=f"🎵 {ctx.author.mention}: {message}"
        )
        await ctx.send(embed=embed)

    async def disconnect_nodes(self) -> None:
        return await self.pomice.disconnect()

    async def start_nodes(self) -> pomice.Node:
        """start the pomice nodes"""
        await self.pomice.create_node(
            bot=self.bot,
            host="127.0.0.1",
            port=2333,
            password="suckdick1337",
            spotify_client_id="f567fb50e0b94b4e8224d2960a00e3ce",
            spotify_client_secret="f4294b7b837940f996b3a4dcf5230628",
            secure=False,
            identifier="MAIN",
        )
        print("music node is ready")

    @Cog.listener()
    async def on_pomice_track_end(self, player: Player, track, _):
        await player.do_next()

    @Cog.listener()
    async def on_pomice_track_stuck(self, player: Player, track, _):
        await player.do_next()

    @Cog.listener()
    async def on_pomice_track_exception(self, player: Player, track, _):
        await player.do_next()

    @Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        if before.channel:
            if member.guild.me in before.channel.members:
                if len(before.channel.members) == 1:
                    await member.guild.voice_client.disconnect(force=True)

    @command()
    @is_voice()
    @bot_is_voice()
    async def stop(self, ctx: PretendContext):
        """leave the voice channel"""
        await ctx.voice_client.kill()

    @command()
    @is_voice()
    @bot_is_voice()
    async def shuffle(self, ctx: PretendContext):
        """
        shuffle the whole queue
        """

        player: Player = ctx.voice_client
        player.shuffle()
        await ctx.send_success("Shuffling the whole queue")

    @command(aliases=["q"])
    @is_voice()
    @bot_is_voice()
    async def queue(self, ctx: PretendContext):
        """
        get a list of the upcoming songs
        """

        player: Player = ctx.voice_client
        playing = f"{'Looping' if player.loop else 'Playing'} [***{player.current.title}***]({player.current.uri}) by **{player.current.author}**"

        if player.queue.get_queue():
            tracks = [
                f"[**{track.title}**]({track.uri})"
                for track in player.queue.get_queue()
            ]
            embeds = []
            queue_length = len(player.queue.get_queue())

            for m in utils.as_chunks(tracks, 10):
                embed = Embed(color=self.bot.color, description=playing).add_field(
                    name=f"Tracks ({queue_length})", value="\n".join([l for l in m])
                )
                embeds.append(embed)

            await ctx.paginator(embeds)
        else:
            embed = Embed(color=self.bot.color, description=playing)

            await ctx.send(embed=embed)

    @command()
    @is_voice()
    @bot_is_voice()
    async def resume(self, ctx: PretendContext):
        """
        resume the current song
        """

        player: Player = ctx.voice_client
        await player.set_pause(False)
        return await ctx.send_success("Resumed the song")

    @command()
    @is_voice()
    @bot_is_voice()
    async def pause(self, ctx: PretendContext):
        """
        Pause the current song
        """

        player: Player = ctx.voice_client
        await player.set_pause(True)
        return await ctx.send_success("Paused the song")

    @command(aliases=["next"])
    @is_voice()
    @bot_is_voice()
    async def skip(self, ctx: PretendContext):
        """
        skip to the next song
        """

        player: Player = ctx.voice_client
        player.loop = False
        player.awaiting = True
        await player.stop()

    @command(aliases=["vol"])
    @is_voice()
    @bot_is_voice()
    async def volume(self, ctx: PretendContext, volume: EligibleVolume):
        """
        set the volume to the current playing song
        """

        player: Player = ctx.voice_client
        await player.set_volume(volume=volume)
        await self.music_send(ctx, f"Volume set to **{volume}**")

    @command()
    @is_voice()
    @bot_is_voice()
    async def loop(self, ctx: PretendContext):
        """
        Loop the current playing song
        """

        player: Player = ctx.voice_client

        if not player.is_playing:
            return await ctx.send_error("No track is playing right now")

        if not player.loop:
            player.loop = True
            return await self.music_send(
                ctx,
                f"Looping [**{player.current_track.title}**]({player.current_track.uri})",
            )
        else:
            player.loop = False
            return await self.music_send(
                ctx,
                f"Removed the loop for [**{player.current_track.title}**]({player.current_track.uri})",
            )

    @command(aliases=["p"])
    @is_voice()
    async def play(self, ctx: PretendContext, *, query: str):
        """
        play a song in the voice channel
        """

        if not ctx.voice_client:
            player = await ctx.author.voice.channel.connect(cls=Player, self_deaf=True)
        else:
            player: Player = ctx.voice_client

        player.set_context(ctx)
        player.awaiting = True
        try:
            results = await player.get_tracks(query=query, ctx=ctx)
        except Exception as e:
            return await ctx.send_warning("There was an issue fetching that track.")
        if not results:
            await ctx.send_warning("No song found")

        if isinstance(results, pomice.Playlist):
            for track in results.tracks:
                player.queue.put(track)
            track = None
            await self.music_send(
                ctx, f"Added **{len(results.tracks)}** songs to the queue"
            )
        else:
            track = results[0]
            if player.is_playing:
                player.queue.put(track)
                await self.music_send(
                    ctx, f"Added [**{track.title}**]({track.uri}) to the queue"
                )

        if not player.is_playing:
            player.current_track = track
            await player.do_next(track)


async def setup(bot) -> None:
    await bot.add_cog(Music(bot))
