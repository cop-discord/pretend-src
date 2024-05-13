import re
import emoji
import string
import matplotlib

from discord.ext.commands import (
    Converter,
    BadArgument,
    MemberConverter,
    RoleConverter,
    BotMissingPermissions,
)

from pydantic import BaseModel
from .helpers import PretendContext


class ColorSchema(BaseModel):
    """
    Schema for colors
    """

    hex: str
    value: int


class AnyEmoji(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if emoji.is_emoji(argument):
            return argument

        emojis = re.findall(
            r"<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>",
            argument,
        )

        if len(emojis) == 0:
            raise BadArgument(f"**{argument}** is **not** an emoji")

        emoj = emojis[0]
        format = ".gif" if emoj[0] == "a" else ".png"
        return await ctx.bot.session.get_bytes(
            f"https://cdn.discordapp.com/emojis/{emoj[2]}{format}"
        )


class EligibleVolume(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            volume = int(argument)
        except ValueError:
            raise BadArgument("This is **not** a number")

        if volume < 0 or volume > 500:
            raise BadArgument("Volume has to be between **0** and **500**")

        return volume


class HexColor(Converter):
    async def convert(self, ctx: PretendContext, argument: str) -> ColorSchema:
        if argument in ["pfp", "avatar"]:
            dominant = await ctx.bot.dominant_color(ctx.author.display_avatar)
            payload = {"hex": hex(dominant).replace("0x", "#"), "value": dominant}
        else:
            color = matplotlib.colors.cnames.get(argument)

            if not color:
                color = argument.replace("#", "")
                digits = set(string.hexdigits)
                if not all(c in digits for c in color):
                    raise BadArgument("This is not a hex code")

            color = color.replace("#", "")
            payload = {"hex": f"#{color}", "value": int(color, 16)}

        return ColorSchema(**payload)


class AbleToMarry(MemberConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            member = await super().convert(ctx, argument)
        except BadArgument:
            raise BadArgument("This is **not** a member")

        if member == ctx.author:
            raise BadArgument("You cannot marry yourself")

        if member.bot:
            raise BadArgument("You cannot marry a bot")

        if await ctx.bot.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", member.id
        ):
            raise BadArgument(f"**{member}** is already married")

        if await ctx.bot.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", ctx.author.id
        ):
            raise BadArgument(
                "You are already **married**. Are you trying to cheat?? 🤨"
            )

        return member


class NoStaff(MemberConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            member = await super().convert(ctx, argument)
        except BadArgument:
            raise BadArgument("Member not found")

        if ctx.guild.me.top_role.position <= member.top_role.position:
            raise BadArgument("The bot cannot manage this member")

        if ctx.command.qualified_name in ["ban", "kick", "softban", "strip"]:
            if ctx.author.id == member.id:
                if ctx.author.id == ctx.guild.owner_id:
                    raise BadArgument("You cannot execute this command on yourself")
        else:
            if ctx.author.id == member.id:
                return member

        if ctx.author.id == ctx.guild.owner_id:
            return member
        if member.id == ctx.guild.owner_id:
            raise BadArgument("You cannot punish the server owner")
        if ctx.author.top_role.position <= member.top_role.position:
            raise BadArgument(f"You cannot manage **{member.mention}**")

        return member


class LevelMember(MemberConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            member = await super().convert(ctx, argument)
        except BadArgument:
            raise BadArgument("Member not found")

        if ctx.author.id == member.id:
            return member

        if member.id == ctx.guild.owner_id:
            raise BadArgument("You cannot change the level stats of the server owner")
        if ctx.author.id == ctx.guild.owner_id:
            return member
        if ctx.author.top_role.position <= member.top_role.position:
            raise BadArgument(f"You cannot manage **{member.mention}**")

        return member


class CounterMessage(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if not "{target}" in argument:
            raise BadArgument("{target} variable is **missing** from the channel name")

        return argument


class ChannelType(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if not argument in ["voice", "stage", "text", "category"]:
            raise BadArgument(f"**{argument}** is not a **valid** channel type")

        return argument


class CounterType(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if not argument in ["members", "voice", "boosters", "humans", "bots"]:
            raise BadArgument(f"**{argument}** is not an **available** counter")

        return argument


class NewRoleConverter(RoleConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            role = await super().convert(ctx, argument)
        except BadArgument:
            role = ctx.find_role(argument)
            if not role:
                raise BadArgument("Role not found")

        if not ctx.guild.me.guild_permissions.manage_roles:
            raise BotMissingPermissions(
                "The bot doesn't have proper permissions to execute this command"
            )

        if role.position >= ctx.guild.me.top_role.position:
            raise BadArgument("This role is over my highest role")

        if not role.is_assignable():
            raise BadArgument("This role cannot be added to anyone by me")

        if ctx.author.id == ctx.guild.owner_id:
            return role

        if role.position >= ctx.author.top_role.position:
            raise BadArgument("You cannot manage this role")

        return role


class EligibleEconomyMember(MemberConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        try:
            member = await super().convert(ctx, argument)
        except BadArgument:
            raise BadArgument("Member **not** found")

        if member.id == ctx.author.id:
            raise BadArgument("You cannot transfer to yourself")

        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM economy WHERE user_id = $1", member.id
        )

        if not check:
            raise BadArgument("This member does not have an economy account created")

        return member


class CardAmount(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        check = await ctx.bot.db.fetchrow(
            "SELECT card FROM economy WHERE user_id = $1", ctx.author.id
        )

        if argument.lower() in ["inf", "nan"]:
            raise BadArgument("This is not a number")

        if argument.lower() == "all":
            amount = round(check[0], 2)

        else:
            try:
                amount = float(argument)
            except:
                raise BadArgument("This is not a number")

        if argument[::-1].find(".") > 2:
            raise BadArgument("The number cannot have more than **2** decimals")

        if amount < 0:
            raise BadArgument(f"You cannot use less than **0** {self.cash}")

        if check[0] < amount:
            raise BadArgument("You do not have enough **money** to use")

        return amount


class CashAmount(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        cash = await ctx.bot.db.fetchval(
            "SELECT cash FROM economy WHERE user_id = $1", ctx.author.id
        )

        if cash < 0:
            raise BadArgument("Your balance is negative dude :skull:")

        if argument.lower() in ["nan", "inf"]:
            raise BadArgument("This is not a number")

        if argument.lower() == "all":
            amount = round(cash, 2)
        else:
            try:
                amount = float(argument)
            except:
                raise BadArgument("This is not a number")

        if argument[::-1].find(".") > 2:
            raise BadArgument("The number cannot have more than **2** decimals")

        if amount < 0:
            raise BadArgument(f"You cannot use less than **0** {self.cash}")

        if cash < amount:
            raise BadArgument("You do not have enough **cash** to use")

        return amount


class Punishment(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        if not argument in ["ban", "kick", "strip"]:
            raise BadArgument(
                f"**{argument}** is **not** a valid punishment\nThe valid ones are: ban, kick and strip"
            )

        return argument
