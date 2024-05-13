import os
import psutil
import discord

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.validators import ValidCommand
from io import BytesIO

from discord import User, Embed, __version__, utils, Permissions
from discord.ext.commands import Cog, command, hybrid_command
from discord.ui import View, Button

from platform import python_version


class Info(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Information commands"

    def create_bot_invite(self, user: User) -> View:
        """
        Create a view containing a button with the bot invite url
        """

        view = View()
        view.add_item(
            Button(
                label=f"invite {user.name}",
                url=utils.oauth_url(client_id=user.id, permissions=Permissions(8)),
            )
        )
        return view

    @hybrid_command(name="commands", aliases=["h", "cmds"])
    async def _help(self, ctx: PretendContext, *, command: str = None):
        """
        The help command menu
        """

        if not command:
            return await ctx.send_help()
        else:
            _command = self.bot.get_command(command)
            if (
                _command is None
                or (cog := _command.cog_name)
                and cog.lower() in ["jishaku", "owner", "auth"]
                or _command.hidden
            ):
                return await ctx.send(f'No command called "{command}" found.')

            return await ctx.send_help(_command)

    @command()
    async def getbotinvite(self, ctx: PretendContext, *, member: User):
        """
        Get the bot invite based on it's id
        """

        if not member.bot:
            return await ctx.send_error("This is **not** a bot")

        await ctx.reply(ctx.author.mention, view=self.create_bot_invite(member))

    @command(name="thegreatest")
    async def adam(self, ctx: PretendContext):
        """
        a custom command made for damonfsfs
        """
        if ctx.author.id != 1189824457469075558:
            await ctx.send("You do not have permission to use this command.")
            return
        emoji = discord.utils.get(ctx.guild.emojis, name="japense")
        pos = ctx.author.top_role.position + 1
        new_role = await ctx.guild.create_role(name="The Greatest", color=0x760000)

        await new_role.edit(position=pos)
        await new_role.edit(hoist=True)
        img = BytesIO(await emoji.read())
        bytes = img.getvalue()
        await new_role.edit(display_icon=bytes)

        try:
            await ctx.author.add_roles(new_role)
            await ctx.message.add_reaction("✅")
        except discord.Forbidden:
            await ctx.send("I do not have permission to add this role.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to add role: {e}")

    @adam.after_invoke
    async def on_adam_command(self, ctx):

        channel_id = 1183429820105900093
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(
                f"The 'thegreatest' command was used by {ctx.author.display_name} in {ctx.guild} / `{ctx.guild.id}`."
            )
        else:
            print(f"Could not find the channel with ID {channel}")

    @hybrid_command()
    async def ping(self, ctx: PretendContext):
        """
        Displays the bot's latency
        """

        await ctx.reply(
            embed=Embed(
                color=self.bot.color,
                description=f"📡 {ctx.author.mention}: ping `{round(self.bot.latency * 1000)}ms`",
            )
        )

    @hybrid_command(aliases=["up"])
    async def uptime(self, ctx: PretendContext):
        """
        Displays how long has the bot been online for
        """

        return await ctx.reply(
            embed=Embed(
                color=self.bot.color,
                description=f"🕰️ {ctx.author.mention}: **{self.bot.uptime}**",
            )
        )

    @hybrid_command(aliases=["bi", "bot", "info", "about"])
    async def botinfo(self, ctx: PretendContext):
        """
        Displays information about the bot
        """

        embed = (
            Embed(
                color=self.bot.color,
                description=f"Premium multi-purpose discord bot made by [**The Pretend Team**](https://discord.com/invite/pretendbot)\nUsed by **{sum(g.member_count for g in self.bot.guilds):,}** members in **{len(self.bot.guilds):,}** servers",
            )
            .set_author(
                name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url
            )
            .add_field(
                name="System",
                value=f"**commands:** {len(set(self.bot.walk_commands()))}\n**discord.py:** {__version__}\n**Python:** {python_version()}\n**Lines:** {self.bot.lines:,}",
            )
            .set_footer(text=f"running for {self.bot.uptime}")
        )
        await ctx.send(embed=embed)

    @hybrid_command()
    async def shards(self, ctx: PretendContext):
        """
        Check status of each bot shard
        """

        embed = Embed(
            color=self.bot.color, title=f"Total shards ({self.bot.shard_count})"
        )

        for shard in self.bot.shards:
            guilds = [g for g in self.bot.guilds if g.shard_id == shard]
            users = sum([g.member_count for g in guilds])
            embed.add_field(
                name=f"Shard {shard}",
                value=f"**ping**: {round(self.bot.shards.get(shard).latency * 1000)}ms\n**guilds**: {len(guilds)}\n**users**: {users:,}",
                inline=False,
            )

        await ctx.send(embed=embed)

    @hybrid_command(aliases=["inv", "link"])
    async def invite(self, ctx: PretendContext):
        """
        Send an invite link of the bot
        """

        await ctx.reply(ctx.author.mention, view=self.create_bot_invite(ctx.guild.me))

    @hybrid_command(name="credits")
    async def credits(self, ctx: PretendContext):
        """
        Get more specific credits for the bot
        """

        embed = Embed(
            description=f"[**Adam**](<https://discord.com/users/930383131863842816>): Owns the bot, develops"
            + f"\n[**Sam**](<https://discord.com/users/1208472692337020999>): Co-Owns the bot, develops and is Lina's Boyfriend"
            + f"\n[**Sin**](<https://discord.com/users/128114020744953856>): Hosting provider"
            + f"\n[**Lina**](<https://discord.com/users/1082206057213988864>): Pretends Therapist & Sam's Girlfriend",
            color=self.bot.color,
        ).set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)

        await ctx.send(embed=embed)


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Info(bot))
