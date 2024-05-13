import re
import json
import datetime
import google.generativeai as genai

from tools.bot import Pretend
from tools.converters import NoStaff
from tools.helpers import PretendContext
from tools.validators import ValidReskinName
from tools.predicates import has_perks, create_reskin

from discord import User, utils, Embed, Member, AllowedMentions, Interaction
from discord.ext import commands
from discord.ext.commands import (
    Cog,
    command,
    group,
    has_guild_permissions,
    bot_has_guild_permissions,
    Author,
    cooldown,
    hybrid_command,
)


class Donor(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Premium commands"

    def shorten(self, value: str, length: int = 32):
        if len(value) > length:
            value = value[: length - 2] + ("..." if len(value) > length else "").strip()
        return value

    @Cog.listener()
    async def on_user_update(self, before: User, after: User):
        if before.discriminator == "0":
            if before.name != after.name:
                if not self.bot.cache.get("pomelo"):
                    await self.bot.cache.set(
                        "pomelo",
                        [
                            {
                                "username": before.name,
                                "time": utils.format_dt(
                                    datetime.datetime.now(), style="R"
                                ),
                            }
                        ],
                    )
                else:
                    lol = self.bot.cache.get("pomelo")
                    lol.append(
                        {
                            "username": before.name,
                            "time": utils.format_dt(datetime.datetime.now(), style="R"),
                        }
                    )
                    await self.bot.cache.set("pomelo", lol)

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if str(before.nick) != str(after.nick):
            if nickname := await self.bot.db.fetchval(
                "SELECT nickname FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                before.guild.id,
                before.id,
            ):
                if after.nick != nickname:
                    await after.edit(
                        nick=nickname, reason="Force nickname applied to this member"
                    )

    @command(aliases=["pomelo", "handles"], brief="donor")
    @has_perks()
    async def lookup(self, ctx: PretendContext):
        """get the most recent handles"""
        if not self.bot.cache.get("pomelo"):
            return await ctx.send_error("There is nothing to see here")
        pomelo = self.bot.cache.get("pomelo")
        return await ctx.paginate(
            [f"{m['username']} - {m['time']}" for m in pomelo[::-1]],
            f"Pomelo Usernames ({len(pomelo)})",
        )

    @command(aliases=["sp"], brief="donor")
    @has_perks()
    async def selfpurge(self, ctx: PretendContext, amount: int = 100):
        """delete your own messages"""
        await ctx.channel.purge(
            limit=amount,
            check=lambda m: m.author.id == ctx.author.id and not m.pinned,
            bulk=True,
        )

    @command(
        brief="manage nicknames & donor",
        aliases=["forcenick", "fn"],
        usage="forcenick @sent bro\nnone passed as a nickname removes the force nickname",
    )
    @has_perks()
    @has_guild_permissions(manage_nicknames=True)
    @bot_has_guild_permissions(manage_nicknames=True)
    async def forcenickname(
        self, ctx: PretendContext, member: NoStaff, *, nickname: str
    ):
        """lock a nickname to a member"""
        if nickname.lower() == "none":
            if await self.bot.db.fetchrow(
                "SELECT * FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                member.id,
            ):
                await self.bot.db.execute(
                    "DELETE FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id,
                    member.id,
                )
                await member.edit(
                    nick=None, reason="Removed the force nickname from this member"
                )
                return await ctx.send_success("Removed the nickname from this member")
            else:
                return await ctx.send_warning(
                    "There is no force nickname assigned for this member"
                )
        else:
            if await self.bot.db.fetchrow(
                "SELECT * FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                member.id,
            ):
                await self.bot.db.execute(
                    "UPDATE force_nick SET nickname = $1 WHERE guild_id = $2 AND user_id = $3",
                    nickname,
                    ctx.guild.id,
                    member.id,
                )
                await member.edit(
                    nick=nickname, reason="Force nickname applied to this member"
                )
            else:
                await member.edit(
                    nick=nickname, reason="Force nickname applied to this member"
                )
                await self.bot.db.execute(
                    "INSERT INTO force_nick VALUES ($1,$2,$3)",
                    ctx.guild.id,
                    member.id,
                    nickname,
                )
            await ctx.send_success(
                f"Force nicknamed {member.mention} to **{nickname}**"
            )

    @group(invoke_without_command=True)
    async def reskin(self, ctx: PretendContext):
        await ctx.create_pages()

    @reskin.command(name="enable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def reskin_enable(self, ctx: PretendContext):
        """enable reskin feature in your server"""
        if await self.bot.db.fetchrow(
            "SELECT * FROM reskin_enabled WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_warning("Reskin is **already** enabled")

        await self.bot.db.execute(
            "INSERT INTO reskin_enabled VALUES ($1)", ctx.guild.id
        )
        return await ctx.send_success("Reskin is now enabled")

    @reskin.command(name="disable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def reskin_disable(self, ctx: PretendContext):
        """disable the reskin feature in your server"""
        if not await self.bot.db.fetchrow(
            "SELECT * FROM reskin_enabled WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_warning("Reskin is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM reskin_enabled WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success("Reskin is now disabled")

    @reskin.command(name="name", brief="donor")
    @has_perks()
    @create_reskin()
    async def reskin_name(self, ctx: PretendContext, *, name: ValidReskinName):
        """edit your reskin name"""
        await self.bot.db.execute(
            "UPDATE reskin SET username = $1 WHERE user_id = $2", name, ctx.author.id
        )
        return await ctx.send_success(f"Updated your reskin name to **{name}**")

    @reskin.command(name="avatar", brief="donor", aliases=["icon", "pfp", "av"])
    @has_perks()
    @create_reskin()
    async def reskin_avatar(self, ctx: PretendContext, url: str = None):
        """change your reskin's avatar"""
        if url is None:
            url = await ctx.get_attachment()
            if not url:
                return ctx.send_help(ctx.command)
            else:
                url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The image provided is not an url")

        await self.bot.db.execute(
            "UPDATE reskin SET avatar_url = $1 WHERE user_id = $2", url, ctx.author.id
        )
        return await ctx.send_success(f"Updated your reskin [**avatar**]({url})")

    @reskin.command(name="remove", brief="donor", aliases=["delete", "reset"])
    async def reskin_delete(self, ctx: PretendContext):
        """delete your reskin"""

        async def yes_callback(interaction: Interaction):
            await self.bot.db.execute(
                "DELETE FROM reskin WHERE user_id = $1", ctx.author.id
            )
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{self.bot.yes} {ctx.author.mention}: Removed your **reskin**",
                    color=self.bot.yes_color,
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction):
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{ctx.author.mention}: Cancelling action...",
                    color=self.bot.color,
                ),
                view=None,
            )

        return await ctx.confirmation_send(
            f"Are you sure you want to **remove** your reskin?",
            yes_callback,
            no_callback,
        )

    @hybrid_command(name="chatgpt", aliases=["chat", "gpt", "ask"], brief="donor")
    @has_perks()
    @cooldown(1, 5, commands.BucketType.user)
    async def chatgpt(self, ctx: PretendContext, *, query: str):
        """
        Talk to AI
        """

        async with ctx.channel.typing():
            genai.configure(api_key="AIzaSyCDSm6b1aI84TJtzWKzdb6oVozeWe3etD8")
            model = genai.GenerativeModel("gemini-pro")

            response = model.generate_content(query)
            await ctx.send(response.text, allowed_mentions=AllowedMentions.none())


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Donor(bot))
