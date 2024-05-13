import json
import asyncio
import datetime

from tools.predicates import has_perks, lastfm_user_exists
from tools.handlers.lastfmhandler import Spotify, Handler
from tools.validators import ValidLastFmName
from tools.helpers import PretendContext
from tools.bot import Pretend

from io import BytesIO
from typing import Literal
from discord import Message, Embed, User, Member, File
from discord.ext.commands import Cog, group, MissingRequiredArgument, Author, command


class Lastfm(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.emoji = "<:lastfm:1188946307704959079>"
        self.description = "Last.Fm Integration commands"
        self.lastfmhandler = Handler("43693facbb24d1ac893a7d33846b15cc")
        self.spotify = Spotify(self.bot)

    async def lastfm_replacement(self, user: str, params: str) -> str:
        a = await self.lastfmhandler.get_tracks_recent(user, 1)
        userinfo = await self.lastfmhandler.get_user_info(user)
        userpfp = self.bot.url_encode(userinfo["user"]["image"][2]["#text"])
        artist = a["recenttracks"]["track"][0]["artist"]["#text"]
        try:
            albumplays = await self.lastfmhandler.get_album_playcount(
                user, a["recenttracks"]["track"][0]
            )
        except:
            albumplays = "N/A"
        artistplays = await self.lastfmhandler.get_artist_playcount(user, artist)
        trackplays = (
            await self.lastfmhandler.get_track_playcount(
                user, a["recenttracks"]["track"][0]
            )
            or "N/A"
        )
        album = (
            a["recenttracks"]["track"][0]["album"]["#text"].replace(" ", "+") or "N/A"
        )
        params = (
            params.replace("{track.name}", a["recenttracks"]["track"][0]["name"])
            .replace(
                "{lower(track.name)}", a["recenttracks"]["track"][0]["name"].lower()
            )
            .replace(
                "{track.url}", self.bot.url_encode(a["recenttracks"]["track"][0]["url"])
            )
            .replace("{artist.name}", a["recenttracks"]["track"][0]["artist"]["#text"])
            .replace(
                "{lower(artist.name)}",
                a["recenttracks"]["track"][0]["artist"]["#text"].lower(),
            )
            .replace(
                "{artist.url}",
                self.bot.url_encode(
                    f"https://last.fm/music/{artist.replace(' ', '+')}"
                ),
            )
            .replace(
                "{track.image}",
                self.bot.url_encode(
                    str((a["recenttracks"]["track"][0])["image"][3]["#text"]).replace(
                        "{https", "https"
                    )
                ),
            )
            .replace("{artist.plays}", str(artistplays))
            .replace("{album.plays}", str(albumplays))
            .replace("{track.plays}", str(trackplays))
            .replace(
                "{album.name}", a["recenttracks"]["track"][0]["album"]["#text"] or "N/A"
            )
            .replace(
                "{lower(album.name)}",
                (
                    a["recenttracks"]["track"][0]["album"]["#text"].lower()
                    if a["recenttracks"]["track"][0]["album"]["#text"]
                    else "N/A"
                ),
            )
            .replace(
                "{album.url}",
                self.bot.url_encode(
                    f"https://www.last.fm/music/{artist.replace(' ', '+')}/{album.replace(' ', '+')}"
                )
                or "https://none.none",
            )
            .replace("{username}", user)
            .replace("{scrobbles}", a["recenttracks"]["@attr"]["total"])
            .replace("{useravatar}", userpfp)
            .replace("{lastfm.color}", "#ffff00")
            .replace("{lastfm.emoji}", "<:lastfm:1109454314340110386>")
        )

        return params

    @Cog.listener()
    async def on_message(self, message: Message):
        if message.guild:
            if not message.author.bot:
                if check := await self.bot.db.fetchrow(
                    "SELECT * FROM lastfm WHERE user_id = $1 AND customcmd = $2",
                    message.author.id,
                    message.content,
                ):
                    ctx = await self.bot.get_context(message)
                    return await ctx.invoke(
                        self.bot.get_command("nowplaying"), member=message.author
                    )

    @group(invoke_without_command=True, aliases=["lf"])
    async def lastfm(self, ctx: PretendContext):
        """
        Use the lastfm api integration with the bot
        """

        await ctx.create_pages()

    @lastfm.command(name="set")
    async def lf_set(self, ctx: PretendContext, *, user: ValidLastFmName):
        """
        Log in with your lastfm account to the bot
        """

        mes = await ctx.pretend_send("Logging in...")
        await asyncio.sleep(1)
        embed = Embed(
            color=self.bot.color,
            title=f"Logged in as {user['user']['realname']}",
            description=f"🎸 scrobbles - {int(user['user']['playcount']):,}\n🎶 tracks listened - {int(user['user']['track_count']):,}",
            url=user["user"]["url"],
            timestamp=datetime.datetime.fromtimestamp(
                user["user"]["registered"]["#text"]
            ),
        ).set_author(name=ctx.author.name, icon_url=user["user"]["image"][0]["#text"])

        await mes.edit(embed=embed)

    @lastfm.command(name="remove", aliases=["unset"])
    @lastfm_user_exists()
    async def lf_remove(self, ctx: PretendContext):
        """
        Remove your lastfm account, if you have one registered
        """

        await self.bot.db.execute(
            "DELETE FROM lastfm WHERE user_id = $1", ctx.author.id
        )
        return await ctx.lastfm_send("Removed your **Last.Fm** account")

    @lastfm.command(name="chart", aliases=["c"])
    async def lf_chart(
        self,
        ctx: PretendContext,
        user: Member = Author,
        size: str = "3x3",
        period: Literal[
            "overall", "7day", "1month", "3month", "6month", "12month"
        ] = "overall",
    ):
        """
        Create an album chart of the user's top albums
        """

        username = await self.bot.db.fetchval(
            "SELECT username FROM lastfm WHERE user_id = $1", user.id
        )

        if not username:
            return await ctx.lastfm_send(
                f"{user.mention} does not have a lastfm account"
            )

        params = {"username": username, "size": size, "period": period}

        headers = {"api-key": self.bot.pretend_api}

        x = await self.bot.session.get_json(
            "https://v1.pretend.best/lastfm/chart", params=params, headers=headers
        )

        if detail := x.get("detail"):
            return await ctx.send_error(detail)

        image = await self.bot.session.get_bytes(x["image_url"])
        return await ctx.reply(
            f"{user.mention}'s Last.FM **{size}** album chart ({period})",
            file=File(BytesIO(image), filename="chart.png"),
        )

    @lastfm.command(name="customcommand", aliases=["cc"])
    async def lf_customcommand(self, ctx: PretendContext, *, cmd: str):
        """
        Set a custom alias for lastfm nowplaying command
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM lastfm WHERE user_id = $1", ctx.author.id
        )

        if not check:
            return await ctx.lastfm_send("You don't have a **Last.Fm** account set")

        if cmd.lower() == "none":
            if not check["customcmd"]:
                return await ctx.lastfm_send("You do not have any **custom command**")
            else:
                await self.bot.db.execute(
                    "UPDATE lastfm SET customcmd = $1 WHERE user_id = $2",
                    None,
                    ctx.author.id,
                )
                return await ctx.lastfm_send("Removed your **Last.Fm** custom command")

        await self.bot.db.execute(
            "UPDATE lastfm SET customcmd = $1 WHERE user_id = $2", cmd, ctx.author.id
        )
        return await ctx.lastfm_send(f"You **Last.Fm** custom command set to: {cmd}")

    @lastfm.command(name="variables")
    async def lf_variables(self, ctx: PretendContext):
        """
        Returns variables for lastfm custom embeds
        """

        embeds = [
            Embed(
                color=self.bot.color,
                title="Track Variables",
                description=">>> {track.name} - shows track name\n{lower(track.name)} - track name in lowercase\n{track.url} - shows the track lastfm url\n{track.image} - shows the track image\n{track.plays} - shows the track's plays on your account",
            ),
            Embed(
                color=self.bot.color,
                title="Artist Variables",
                description=">>> {artist.name} - shows the artist's name\n{lower(artist.name)} - artist name in lowercase\n{artist.url} - shows the artist's lastfm url\n{artist.plays} -shows the artist's plays on your account",
            ),
            Embed(
                color=self.bot.color,
                title="Album Variables",
                description=">>> {album.name} - shows the album's name\n{lower(album.name)} - album name in lowercase\n{album.url} - shows the album's lastfm url\n{album.plays} - shows the album's plays on your account",
            ),
            Embed(
                color=self.bot.color,
                title="Other variables",
                description=">>> {scrobbles} - the total number of songs scrobbled on your account\n{username} - your lastfm username\n{useravatar} - your lastfm avatar\n{lastfm.color} - the main color of lastfm logo\n{lastfm.emoji} - the lastfm logo emoji",
            ),
        ]
        await ctx.paginator(embeds)

    @lastfm.group(invoke_without_command=True, name="mode", aliases=["embed"])
    async def lf_mode(self, ctx: PretendContext):
        """
        Design a custom lastfm embed
        """

        await ctx.create_pages()

    @lf_mode.command(name="set", brief="premium")
    @lastfm_user_exists()
    @has_perks()
    async def lf_mode_set(self, ctx: PretendContext, *, code: str):
        """
        Set an embed as the lastfm custom embed
        """

        await self.bot.db.execute(
            "UPDATE lastfm SET embed = $1 WHERE user_id = $2", code, ctx.author.id
        )
        return await ctx.lastfm_send(
            f"Your custom **Last.Fm** embed is configured to\n```{code}```"
        )

    @lf_mode.command(name="remove", brief="premium")
    @lastfm_user_exists()
    @has_perks()
    async def lf_mode_remove(self, ctx: PretendContext):
        """
        Remove your custom lastfm embed
        """

        await self.bot.db.execute(
            "UPDATE lastfm SET embed = $1 WHERE user_id = $2", None, ctx.author.id
        )
        return await ctx.lastfm_send("Removed your **Last.Fm** custom embed")

    @lf_mode.command(name="view", brief="premium")
    @has_perks()
    async def lf_mode_view(self, ctx: PretendContext, *, member: User = Author):
        """
        View your own lastfm embed or someone's lastfm embed
        """

        check = await self.bot.db.fetchrow(
            "SELECT embed FROM lastfm WHERE user_id = $1", member.id
        )
        if not check:
            return await ctx.lastfm_send(
                "The member provided doesn't have a **Last.Fm** account connected"
            )

        embed = Embed(
            color=self.bot.color,
            title=f"{member.name}'s custom lastfm embed",
            description=f"```\n{check[0]}```",
        )
        await ctx.send(embed=embed)

    @lf_mode.command(name="steal", brief="premium")
    @has_perks()
    async def lf_mode_steal(self, ctx: PretendContext, *, member: Member):
        """
        Steal someone's lastfm embed
        """

        if member is ctx.author:
            return await ctx.send("Stealing from yourself doesn't make sense")

        check = await self.bot.db.fetchrow(
            "SELECT embed FROM lastfm WHERE user_id = $1", member.id
        )
        if not check:
            return await ctx.lastfm_send("This member doesn't have a custom embed")

        await self.bot.db.execute(
            "UPDATE lastfm SET embed = $1 WHERE user_id = $2", check[0], ctx.author.id
        )
        return await ctx.lastfm_send(
            f"Stolen {member.mention}'s **Last.Fm** custom embed"
        )

    @lastfm.command(name="reactions")
    @lastfm_user_exists()
    async def lf_reactions(self, ctx: PretendContext, *reactions: str):
        """
        Set custom reactions for the nowplaying command
        """

        if len(reactions) == 0:
            return await ctx.send_help(ctx.command)

        elif len(reactions) == 1:
            if reactions[0] == "default":
                reacts = ["🔥", "🗑️"]
            elif reactions[0] == "none":
                reacts = []
            else:
                reacts = set(reactions)
        else:
            reacts = set(reactions)

        to_dump = json.dumps(list(reacts))
        await self.bot.db.execute(
            "UPDATE lastfm SET reactions = $1 WHERE user_id = $2",
            to_dump,
            ctx.author.id,
        )
        return await ctx.lastfm_send(
            f"Your **Last.Fm** reactions are set as {' '.join(list(reacts)) if len(list(reacts)) > 0 else 'none'}"
        )

    @lastfm.command(name="spotify", aliases=["sp"])
    async def lf_spotify(self, ctx: PretendContext, *, member: Member = Author):
        """
        Look up for your nowplaying lastfm song on spotify
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM lastfm WHERE user_id = $1", member.id
        )

        if not check:
            return await ctx.lastfm_send(
                "There is no **last.fm** account linked for this member"
            )

        user = check["username"]
        a = await self.lastfmhandler.get_tracks_recent(user, 1)
        await ctx.send(
            await self.spotify.search(
                f"{a['recenttracks']['track'][0]['name']} {a['recenttracks']['track'][0]['artist']['#text']}"
            )
        )

    @lastfm.command(name="topartists", aliases=["ta", "tar"])
    async def lf_topartists(self, ctx, member: Member = Author):
        """
        Returns a member's top 10 artists
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM lastfm WHERE user_id = $1", member.id
        )
        if check:
            user = check["username"]
            data = await self.lastfmhandler.get_top_artists(user, 10)
            mes = "\n".join(
                f"`{i+1}` **[{data['topartists']['artist'][i]['name']}]({data['topartists']['artist'][i]['url']})** {data['topartists']['artist'][i]['playcount']} plays"
                for i in range(10)
            )
            embed = Embed(description=mes, color=self.bot.color)
            embed.set_thumbnail(url=member.display_avatar)
            embed.set_author(
                name=f"{user}'s overall top artists", icon_url=member.display_avatar
            )
            return await ctx.send(embed=embed)
        return await ctx.lastfm_send(
            "There is no **last.fm** account linked for this member"
        )

    @lastfm.command(name="toptracks", aliases=["tt"])
    async def lf_toptracks(self, ctx: PretendContext, *, member: Member = Author):
        """
        Returns a member's top 10 tracks
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM lastfm WHERE user_id = {}".format(member.id)
        )
        if check:
            user = check["username"]
            jsonData = await self.lastfmhandler.get_top_tracks(user, 10)
            embed = Embed(
                description="\n".join(
                    f"`{i+1}` **[{jsonData['toptracks']['track'][i]['name']}]({jsonData['toptracks']['track'][i]['url']})** {jsonData['toptracks']['track'][i]['playcount']} plays"
                    for i in range(10)
                ),
                color=self.bot.color,
            )
            embed.set_thumbnail(url=ctx.message.author.avatar)
            embed.set_author(
                name=f"{user}'s overall top tracks", icon_url=ctx.message.author.avatar
            )
            return await ctx.send(embed=embed)
        return await ctx.lastfm_send(
            "There is no **last.fm** account linked for this member"
        )

    @lastfm.command(name="topalbums", aliases=["tal"])
    async def lf_topalbums(self, ctx: PretendContext, *, member: Member = Author):
        """
        Returns a member's top 10 albums
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM lastfm WHERE user_id = {}".format(member.id)
        )
        if check:
            user = check["username"]
            jsonData = await self.lastfmhandler.get_top_albums(user, 10)
            embed = Embed(
                description="\n".join(
                    f"`{i+1}` **[{jsonData['topalbums']['album'][i]['name']}]({jsonData['topalbums']['album'][i]['url']})** {jsonData['topalbums']['album'][i]['playcount']} plays"
                    for i in range(10)
                ),
                color=self.bot.color,
            )
            embed.set_thumbnail(url=ctx.message.author.avatar)
            embed.set_author(
                name=f"{user}'s overall top albums", icon_url=ctx.message.author.avatar
            )
            return await ctx.send(embed=embed)
        return await ctx.lastfm_send(
            "There is no **last.fm** account linked for this member"
        )

    @lastfm.command(name="howto", help="lastfm")
    async def lf_howto(self, ctx: PretendContext):
        """
        A short guide on how to register your lastfm account
        """

        await ctx.send(
            f"1) create an account at https://last.fm\n2) link your **spotify** account to your **last.fm** account\n3) use the command `{ctx.clean_prefix}lf set [your lastfm username]`\n4) while you listen to your songs, you can use the `{ctx.clean_prefix}nowplaying` command"
        )

    @lastfm.command(name="user", aliases=["ui"])
    async def lf_user(self, ctx: PretendContext, user: User = Author):
        """
        Information about a member's lastfm user
        """

        async with ctx.typing():
            check = await self.bot.db.fetchrow(
                "SELECT username FROM lastfm WHERE user_id = $1", user.id
            )
            username = check["username"]

            if not check:
                return await ctx.send_warning(
                    f"{'You don' if user == ctx.author else f'**{user}** doesn'}'t have a **last.fm** account connected"
                )

            info = await self.lastfmhandler.get_user_info(username)
            try:
                i = info["user"]
                name = i["name"]
                age = int(i["age"])
                subscriber = f"{'false' if i['subscriber'] == '0' else 'true'}"
                realname = i["realname"]
                playcount = int(i["playcount"])
                artistcount = int(i["artist_count"])
                trackcount = int(i["track_count"])
                albumcount = int(i["album_count"])
                image = i["image"][3]["#text"]
                embed = (
                    Embed(color=self.bot.color)
                    .set_footer(text=f"{playcount:,} total scrobbles")
                    .set_thumbnail(url=image)
                    .set_author(name=f"{name}", icon_url=image)
                    .add_field(
                        name=f"Plays",
                        value=f"**artists:** {artistcount:,}\n**plays:** {playcount:,}\n**tracks:** {trackcount:,}\n**albums:** {albumcount:,}",
                        inline=False,
                    )
                    .add_field(
                        name=f"Info",
                        value=f"**name:** {realname}\n**registered:** <t:{int(i['registered']['#text'])}:R>\n**subscriber:** {subscriber}\n**age:** {age:,}",
                        inline=False,
                    )
                )
                await ctx.send(embed=embed)
            except TypeError:
                return await ctx.lastfm_send(
                    "This user doesn't have a **last.fm** account connected"
                )

    @lastfm.command(name="whoknows", aliases=["wk"])
    async def lf_whoknows(self, ctx: PretendContext, *, artist: str = None):
        """
        Get the top listeners of a certain artist from the server
        """

        check = await self.bot.db.fetchrow(
            "SELECT username FROM lastfm WHERE user_id = $1", ctx.author.id
        )
        if not check:
            return await ctx.lastfm_send(
                "You don't have a **Last.Fm** account connected"
            )

        if artist is None:
            a = await self.lastfmhandler.get_tracks_recent(check[0], 1)
            artist = a["recenttracks"]["track"][0]["artist"]["#text"]

        async with ctx.typing():
            wk = []
            results = await self.bot.db.fetch(
                f"SELECT * FROM lastfm WHERE user_id IN ({','.join([str(m.id) for m in ctx.guild.members])})"
            )
            for r in results:
                wk.append(
                    tuple(
                        [
                            ctx.guild.get_member(r["user_id"]).name,
                            await self.lastfmhandler.get_artist_playcount(
                                r["username"], artist
                            ),
                            f"https://last.fm/user/{r['username']}",
                        ]
                    )
                )

        await ctx.paginate(
            [
                f"[**{result[0]}**]({result[2]}) has **{result[1]}** plays"
                for result in sorted(wk, key=lambda m: int(m[1]), reverse=True)
                if int(result[1]) > 0
            ],
            f"Who knows {artist}",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @lastfm.command(name="globalwhoknows", aliases=["gwk"])
    async def lf_globalwhoknows(self, ctx: PretendContext, *, artist: str = None):
        """
        Get the top listeners of a certain artist
        """

        check = await self.bot.db.fetchrow(
            "SELECT username FROM lastfm WHERE user_id = $1", ctx.author.id
        )
        if not check:
            return await ctx.lastfm_send(
                "You don't have a **Last.Fm** account connected"
            )

        if artist is None:
            a = await self.lastfmhandler.get_tracks_recent(check[0], 1)
            artist = a["recenttracks"]["track"][0]["artist"]["#text"]

        async with ctx.typing():
            wk = []
            results = await self.bot.db.fetch(f"SELECT * FROM lastfm")
            for r in results:
                try:
                    wk.append(
                        tuple(
                            [
                                self.bot.get_user(r["user_id"]).name,
                                await self.lastfmhandler.get_artist_playcount(
                                    r["username"], artist
                                ),
                                f"https://last.fm/user/{r['username']}",
                            ]
                        )
                    )
                except:
                    continue

        await ctx.paginate(
            [
                f"[**{result[0]}**]({result[2]}) has **{result[1]}** plays"
                for result in sorted(wk, key=lambda m: int(m[1]), reverse=True)
                if int(result[1]) > 0
            ],
            f"Who knows {artist}",
        )

    @lastfm.command(name="cover", aliases=["image"])
    async def lf_cover(self, ctx: PretendContext, *, member: Member = Author):
        """
        Get the cover image of your lastfm song
        """

        check = await self.bot.db.fetchrow(
            "SELECT username FROM lastfm WHERE user_id = $1", member.id
        )

        if check is None:
            return await ctx.lastfm_send(
                f"{'You don' if member == ctx.author else f'{member.mention} doesn'}'t have a **last.fm** account connected"
            )

        user = check[0]
        a = await self.lastfmhandler.get_tracks_recent(user, 1)
        file = File(
            await self.bot.getbyte(
                (a["recenttracks"]["track"][0])["image"][3]["#text"]
            ),
            filename="cover.png",
        )
        return await ctx.send(f"**{a['recenttracks']['track'][0]['name']}**", file=file)

    @lastfm.command(name="recent")
    async def lf_recent(self, ctx: PretendContext, *, member: Member = Author):
        """
        Shows the top 10 most recent songs on lastfm
        """

        username = await self.bot.db.fetchval(
            "SELECT username FROM lastfm WHERE user_id = $1", member.id
        )

        if not username:
            return await ctx.lastfm_send(
                f"{'You don' if member == ctx.author else f'{member.mention} doesn'}'t have a **last.fm** account connected"
            )

        if cache := self.bot.cache.get(f"lf-recent-{member.id}"):
            tracks = cache
        else:
            recents = await self.lastfmhandler.get_tracks_recent(username)
            tracks = [
                f"[**{a['name']}**](https://last.fm/music/{a['name'].replace(' ', '+')}) by {a['artist']['#text']}"
                for a in list(
                    {v["name"]: v for v in recents["recenttracks"]["track"]}.values()
                )
            ]

            await self.bot.cache.set(f"lf-recent-{member.id}", tracks, 60 * 5)

        await ctx.paginate(
            tracks,
            title=f"{member.name}'s recent tracks",
            author={"name": ctx.author.name, "icon_url": ctx.author.display_avatar.url},
        )

    @command(aliases=["np", "fm"])
    async def nowplaying(self, ctx: PretendContext, *, member: Member = Author):
        """
        Returns the latest song scrobbled on Last.Fm
        """

        check = await self.bot.db.fetchrow(
            "SELECT username, reactions, embed FROM lastfm WHERE user_id = $1",
            member.id,
        )

        if not check:
            return await ctx.lastfm_send(
                f"{'You don' if member.id == ctx.author.id else f'{member.mention} doesn'}'t have a **Last.Fm** account connected"
            )
        user = check[0]

        if check[2]:
            x = await self.bot.embed_build.convert(
                ctx, await self.lastfm_replacement(user, check[2])
            )
            mes = await ctx.send(**x)

        else:
            try:
                a = await asyncio.wait_for(
                    self.lastfmhandler.get_tracks_recent(user, 1), timeout=15
                )
                u = await asyncio.wait_for(
                    self.lastfmhandler.get_user_info(user), timeout=15
                )
            except asyncio.TimeoutError:
                return await ctx.send_warning("Could not connect to LastFM servers.")
            try:
                album = a["recenttracks"]["track"][0]["album"]["#text"]
            except Exception as e:
                return await ctx.send_warning(
                    "There was an issue fetching your current track."
                )
            embed = (
                Embed(color=self.bot.color)
                .set_author(
                    name=user,
                    url=f"https://last.fm/user/{user}",
                    icon_url=u["user"]["image"][2]["#text"],
                )
                .set_thumbnail(url=a["recenttracks"]["track"][0]["image"][2]["#text"])
                .add_field(
                    name="Track",
                    value=f"[**{a['recenttracks']['track'][0]['name']}**](https://last.fm/music/{a['recenttracks']['track'][0]['name'].replace(' ', '+')})",
                    inline=True,
                )
                .add_field(
                    name="Artist",
                    value=f"[**{a['recenttracks']['track'][0]['artist']['#text']}**](https://last.fm/artist/{a['recenttracks']['track'][0]['artist']['#text'].replace(' ', '+')})",
                    inline=True,
                )
                .set_footer(
                    text=f"Playcount: {await self.lastfmhandler.get_track_playcount(user, a['recenttracks']['track'][0])} ∙ Total Scrobbles: {a['recenttracks']['@attr']['total']} {f'∙ Album: {album}' if len(album) > 0 else ''}",
                )
            )
            mes = await ctx.send(embed=embed)

        if check[1] and ctx.guild.me.guild_permissions.add_reactions:
            reactions = json.loads(check[1])

            for r in reactions:
                await mes.add_reaction(r)
                await asyncio.sleep(0.5)


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Lastfm(bot))
