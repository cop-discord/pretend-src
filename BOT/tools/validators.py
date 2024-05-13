import json
import emoji
import humanfriendly

from discord.ext import commands
from tools.helpers import PretendContext

from .handlers.lastfmhandler import Handler
from .exceptions import LastFmException, WrongMessageLink


class ValidNickname(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if argument.lower() == "none":
            return None
        else:
            return argument


class ValidTime(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            time = humanfriendly.parse_timespan(argument)
        except humanfriendly.InvalidTimespan:
            raise commands.BadArgument(f"**{argument}** is an invalid timespan")

        return time


class ValidWebhookCode(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM webhook WHERE guild_id = $1 AND code = $2",
            ctx.guild.id,
            argument,
        )
        if not check:
            raise commands.BadArgument("There is no webhook associated with this code")

        return argument


class ValidEmoji(commands.EmojiConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            emoj = await super().convert(ctx, argument)
        except commands.BadArgument:
            if not emoji.is_emoji(argument):
                raise commands.BadArgument("This is not an emoji")
            emoj = argument
        return emoj


class ValidPermission(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        valid_permissions = [p[0] for p in ctx.author.guild_permissions]

        if not argument in valid_permissions:
            raise commands.BadArgument(
                "This is **not** a valid permission. Please run `;fakepermissions perms` to check all available permissions"
            )

        return argument


class ValidCommand(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if not argument:
            return None

        command = ctx.bot.get_command(argument)
        if not command:
            raise commands.CommandNotFound(f"The command **{argument}** doesn't exist")

        if command.qualified_name in [
            "disablecmd",
            "enablecmd",
        ] or command.cog_name.lower() in ["jishaku", "owner"]:
            raise commands.BadArgument("You cannot disable that command")

        return command.qualified_name


class ValidCog(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if not argument:
            return None

        cog = ctx.bot.get_cog(argument.capitalize())
        if not cog:
            raise commands.BadArgument(f"The module **{argument}** doesn't exist")

        if str(cog.qualified_name).lower() in [
            "jishaku",
            "owner",
            "auth",
            "info",
            "config",
        ]:
            raise commands.CommandRegistrationError("no lol")

        return cog.qualified_name


class ValidAutoreact(commands.EmojiConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            emoj = await super().convert(ctx, argument)
        except commands.BadArgument:
            if not emoji.is_emoji(argument):
                return None

            emoj = argument
        return emoj


class ValidLastFmName(commands.Converter):
    def __init__(self):
        self.lastfmhandler = Handler("43693facbb24d1ac893a7d33846b15cc")

    async def convert(self, ctx: PretendContext, argument: str):
        check = await ctx.bot.db.fetchrow(
            "SELECT username FROM lastfm WHERE user_id = $1", ctx.author.id
        )

        if not await self.lastfmhandler.lastfm_user_exists(argument):
            raise LastFmException("This account **doesn't** exist")

        if check:
            if check[0] == argument:
                raise LastFmException(f"You are **already** registered with this name")
            await ctx.bot.db.execute(
                "UPDATE lastfm SET username = $1 WHERE user_id = $2",
                argument,
                ctx.author.id,
            )
        else:
            await ctx.bot.db.execute(
                """
        INSERT INTO lastfm 
        VALUES ($1,$2,$3,$4,$5)
        """,
                ctx.author.id,
                argument,
                json.dumps(["🔥", "🗑️"]),
                None,
                None,
            )

        return await self.lastfmhandler.get_user_info(argument)


class ValidMessage(commands.MessageConverter):

    async def convert(self, ctx: PretendContext, argument: str):
        try:
            message = await super().convert(ctx, argument)
        except:
            raise commands.BadArgument("This is **not** a message id or a message link")

        if message.guild.id != ctx.guild.id:
            raise WrongMessageLink()

        return message


class ValidReskinName(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        texts = list(
            map(
                lambda t: t.strip(),
                open("./texts/reskin_blacklist.txt", "r").read().splitlines(),
            )
        )

        for arg in argument.split(" "):
            if arg.lower() in texts:
                raise commands.BadArgument("This name cannot be used for reskin")

        return argument
