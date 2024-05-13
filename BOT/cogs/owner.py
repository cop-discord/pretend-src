import os
import random
import string
import asyncio
import datetime
import discord
import json
import importlib

from discord import User, Member, Guild
from discord.ext.commands import Cog, command, is_owner, group
from discord.ext import tasks
from typing import Union
from jishaku.codeblocks import codeblock_converter
from posthog import Posthog

posthog = Posthog(os.environ["hogkey"], "https://hog.semisol.dev")
from tools.bot import Pretend
from tools.helpers import PretendContext

from discord.ext.commands import check


class Owner(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.shard_stats.start()

    @tasks.loop(seconds=10)
    async def shard_stats(self):
        import orjson

        shards = {}
        for shard_id, shard in self.bot.shards.items():
            guilds = [g for g in self.bot.guilds if g.shard_id == shard_id]
            users = sum(list(map(lambda g: g.member_count, guilds)))
            shards[str(shard_id)] = {
                "shard_id": shard_id,
                "shard_name": f"Shard {shard_id}",
                "shard_ping": round(shard.latency * 1000),
                "shard_guild_count": f"{len(guilds):,}",
                "shard_user_count": f"{users:,}",
                "shard_guilds": [str(g.id) for g in guilds],
            }
        await self.bot.redis.set("shards", orjson.dumps(shards))

    async def add_donor_role(self, member: User):
        """add the donor role to a donator"""
        guild = self.bot.get_guild(1177424668328726548)
        user = guild.get_member(member.id)
        if user:
            role = guild.get_role(1183428300807356516)
            await user.add_roles(role, reason="member got donator perks")

    async def remove_donor_role(self, member: User):
        """remove the donator role from a donator"""
        guild = self.bot.get_guild(1177424668328726548)
        user = guild.get_member(member.id)
        if user:
            role = guild.get_role(1183428300807356516)
            await user.remove_roles(role, reason="member got donator perks")

    @Cog.listener()
    async def on_member_join(self, member: Member):
        reason = await self.bot.db.fetchval(
            "SELECT reason FROM globalban WHERE user_id = $1", member.id
        )
        if reason:
            if member.guild.me.guild_permissions.ban_members:
                await member.ban(reason=reason)

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        if member.guild.id == 1177424668328726548:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM donor WHERE user_id = $1 AND status = $2",
                member.id,
                "boosted",
            )
            if check:
                await self.bot.db.execute(
                    "DELETE FROM donor WHERE user_id = $1", member.id
                )
                await self.bot.db.execute(
                    "DELETE FROM reskin WHERE user_id = $1", member.id
                )

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if before.guild.id == 1177424668328726548:
            if (
                before.guild.premium_subscriber_role in before.roles
                and not before.guild.premium_subscriber_role in after.roles
            ):
                check = await self.bot.db.fetchrow(
                    "SELECT * FROM donor WHERE user_id = $1 AND status = $2",
                    before.id,
                    "boosted",
                )
                if check:
                    await self.bot.db.execute(
                        "DELETE FROM reskin WHERE user_id = $1", before.id
                    )
                    await self.bot.db.execute(
                        "DELETE FROM donor WHERE user_id = $1", before.id
                    )

    @Cog.listener()
    async def on_guild_join(self, guild: Guild):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM blacklist WHERE id = $1 AND type = $2", guild.id, "server"
        )
        if check:
            await guild.leave()

    @command(aliases=["py"])
    @is_owner()
    async def eval(self, ctx: PretendContext, *, argument: codeblock_converter):
        return await ctx.invoke(self.bot.get_command("jsk py"), argument=argument)

    @command()
    @is_owner()
    async def restart(self, ctx: PretendContext):
        await ctx.send("restarting the bot...")
        os.system("pm2 restart 0")

    @command()
    @is_owner()
    async def anowner(self, ctx: PretendContext, guild: Guild, member: User):
        """change the antinuke owner in case the real owner cannot access discord"""
        if await self.bot.db.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1", guild.id
        ):
            await self.bot.db.execute(
                "UPDATE antinuke SET owner_id = $1 WHERE guild_id = $2",
                member.id,
                guild.id,
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO antinuke (guild_id, configured, owner_id) VALUES ($1,$2,$3)",
                guild.id,
                "false",
                member.id,
            )
        return await ctx.send_success(
            f"{member.mention} is the **new** antinuke owner for **{guild.name}**"
        )

    @command()
    @is_owner()
    async def guilds(self, ctx: PretendContext):
        """all guilds the bot is in, sorted from the biggest to the smallest"""
        servers = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        return await ctx.paginate(
            [f"{g.name} - {g.member_count:,} members" for g in servers],
            "pretend's servers",
        )

    @command()
    @is_owner()
    async def loadhog(self, ctx: PretendContext):
        """Insert all guilds into posthog"""
        for guild in self.bot.guilds:
            subtype = await get_sub_type(self, guild)
            posthog.group_identify(
                "guild",
                str(guild.id),
                {
                    "name": guild.name,
                    "subscription type": await get_sub_type(self, guild),
                    "member count": guild.member_count,
                },
            )
        return await ctx.send_success("Inserted all guilds into posthog")

    @group(invoke_without_command=True)
    @is_owner()
    async def donor(self, ctx):
        await ctx.create_pages()

    @donor.command(name="add")
    @is_owner()
    async def donor_add(self, ctx: PretendContext, *, member: User):
        """add donator perks to a member"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM donor WHERE user_id = $1", member.id
        )
        if check:
            return await ctx.send_error("This member is **already** a donor")

        await self.add_donor_role(member)
        await self.bot.db.execute(
            "INSERT INTO donor VALUES ($1,$2,$3)",
            member.id,
            datetime.datetime.now().timestamp(),
            "purchased",
        )
        return await ctx.send_success(f"{member.mention} can use donator perks now!")

    @donor.command(name="remove")
    @is_owner()
    async def donor_remove(self, ctx: PretendContext, *, member: User):
        """remove donator perks from a member"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM donor WHERE user_id = $1 AND status = $2",
            member.id,
            "purchased",
        )
        if not check:
            return await ctx.send_error("This member cannot have their perks removed")

        await self.remove_donor_role(member)
        await self.bot.db.execute("DELETE FROM donor WHERE user_id = $1", member.id)
        return await ctx.send_success(f"Removed {member.mention}'s perks")

    @command()
    @is_owner()
    async def mutuals(self, ctx: PretendContext, *, user: User):
        """returns mutual servers between the member and the bot"""
        if len(user.mutual_guilds) == 0:
            return await ctx.send(
                f"This member doesn't share any server with {self.bot.user.name}"
            )

        await ctx.paginate(
            [f"{g.name} ({g.id})" for g in user.mutual_guilds],
            f"Mutual guilds ({len(user.mutual_guilds)})",
            {"name": user.name, "icon_url": user.display_avatar.url},
        )

    @command(name="globalenable")
    @is_owner()
    async def globalenable(self, ctx: PretendContext, cmd: str = ""):
        """
        Globally enable a command.
        """
        if not cmd:
            return await ctx.send_warning("Please provide a command to enable.")
        if cmd in ["*", "all", "ALL"]:
            await self.bot.db.execute("DELETE FROM global_disabled_cmds;")
            return await ctx.send_success(f"All commands have been globally enabled.")
        if not self.bot.get_command(cmd):
            return await ctx.send_warning("Command does not exist.")
        cmd = self.bot.get_command(cmd).name
        await self.bot.db.execute(
            "DELETE FROM global_disabled_cmds WHERE cmd = $1;", cmd
        )
        return await ctx.send_success(f"The command {cmd} has been globally enabled.")

    @command(name="globaldisable")
    @is_owner()
    async def globaldisable(self, ctx: PretendContext, cmd: str = ""):
        """
        Globally disable a command.
        """
        if not cmd:
            return await ctx.send_warning("Please provide a command to disable.")
        if cmd in ["globalenable", "globaldisable"]:
            return await ctx.send_warning("Unable to globally disable this command.")
        if not self.bot.get_command(cmd):
            return await ctx.send_warning("Command does not exist.")
        cmd = self.bot.get_command(cmd).name
        result = await self.bot.db.fetchrow(
            "SELECT disabled FROM global_disabled_cmds WHERE cmd = $1;", cmd
        )
        if result:
            if result.get("disabled"):
                return await ctx.send_warning(
                    "This command is already globally disabled."
                )
        await self.bot.db.execute(
            "INSERT INTO global_disabled_cmds (cmd, disabled, disabled_by) VALUES ($1, $2, $3) "
            "ON CONFLICT (cmd) DO UPDATE SET disabled = EXCLUDED.disabled, disabled_by = EXCLUDED.disabled_by;",
            cmd,
            True,
            str(ctx.author.id),
        )
        return await ctx.send_success(f"The command {cmd} has been globally disabled.")

    @command(name="globaldisabledlist", aliases=["gdl"])
    @is_owner()
    async def globaldisabledlist(self, ctx: PretendContext):
        """
        Show all commands that are globally disabled.
        """
        global_disabled_cmds = await self.bot.db.fetch(
            "SELECT * FROM global_disabled_cmds;"
        )
        if len(global_disabled_cmds) <= 0:
            return await ctx.send_warning("There are no globally disabled commands.")
        disabled_list = [
            f"{obj.get('cmd')} - disabled by <@{obj.get('disabled_by')}>"
            for obj in global_disabled_cmds
        ]
        return await ctx.paginate(
            disabled_list,
            f"Globally Disabled Commands:",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @command(aliases=["trace"])
    @is_owner()
    async def error(self, ctx: PretendContext, code: str):
        """
        View information about an error code
        """

        fl = await self.bot.db.fetch("SELECT * FROM error_codes;")
        error_details = [x for x in fl if x.get("code") == code]

        if len(error_details) == 0 or len(code) != 6:
            return await ctx.send_warning("Please provide a **valid** error code")

        error_details = error_details[0]
        error_details = json.loads(error_details.get("info"))
        guild = self.bot.get_guild(error_details["guild_id"])

        embed = (
            discord.Embed(description=str(error_details["error"]), color=self.bot.color)
            .add_field(name="Guild", value=f"{guild.name}\n`{guild.id}`", inline=True)
            .add_field(
                name="Channel",
                value=f"<#{error_details['channel_id']}>\n`{error_details['channel_id']}`",
                inline=True,
            )
            .add_field(
                name="User",
                value=f"<@{error_details['user_id']}>\n`{error_details['user_id']}`",
                inline=True,
            )
            .add_field(name="Command", value=f"**{error_details['command']}**")
            .add_field(name="Timestamp", value=f"{error_details['timestamp']}")
            .set_author(name=f"Error Code: {code}")
        )

        return await ctx.send(embed=embed)

    @command(aliases=["gban"])
    @is_owner()
    async def globalban(
        self,
        ctx: PretendContext,
        user: User,
        *,
        reason: str = "Globally banned by a bot owner",
    ):
        """ban an user globally"""
        if user.id in [128114020744953856, 1208472692337020999, 930383131863842816]:
            return await ctx.send_error("Do not global ban a bot owner, retard")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM globalban WHERE user_id = $1", user.id
        )
        if check:
            await self.bot.db.execute(
                "DELETE FROM globalban WHERE user_id = $1", user.id
            )
            return await ctx.send_success(
                f"{user.mention} was succesfully globally unbanned"
            )

        mutual_guilds = len(user.mutual_guilds)
        tasks = [
            g.ban(user, reason=reason)
            for g in user.mutual_guilds
            if g.me.guild_permissions.ban_members
            and g.me.top_role > g.get_member(user.id).top_role
            and g.owner_id != user.id
        ]
        await asyncio.gather(*tasks)
        await self.bot.db.execute(
            "INSERT INTO globalban VALUES ($1,$2)", user.id, reason
        )
        return await ctx.send_success(
            f"{user.mention} was succesfully global banned in {len(tasks)}/{mutual_guilds} servers"
        )

    @group(invoke_without_command=True)
    @is_owner()
    async def blacklist(self, ctx):
        await ctx.create_pages()

    @blacklist.command(name="user")
    @is_owner()
    async def blacklist_user(self, ctx: PretendContext, *, user: User):
        """blacklist or unblacklist a member"""
        if user.id in self.bot.owner_ids:
            return await ctx.send_error("Do not blacklist a bot owner, retard")

        try:
            await self.bot.db.execute(
                "INSERT INTO blacklist VALUES ($1,$2)", user.id, "user"
            )
            return await ctx.send_success(f"Blacklisted {user.mention} from pretend")
        except:
            await self.bot.db.execute("DELETE FROM blacklist WHERE id = $1", user.id)
            return await ctx.send_success(f"Unblacklisted {user.mention} from pretend")

    @blacklist.command(name="server")
    @is_owner()
    async def blacklist_server(self, ctx: PretendContext, *, server_id: int):
        """blacklist a server"""
        if server_id in [1177424668328726548]:
            return await ctx.send_error("Cannot blacklist this server")

        try:
            await self.bot.db.execute(
                "INSERT INTO blacklist VALUES ($1,$2)", server_id, "server"
            )
            guild = self.bot.get_guild(server_id)
            if guild:
                await guild.leave()
            return await ctx.send_success(
                f"Blacklisted server {server_id} from pretend"
            )
        except:
            await self.bot.db.execute("DELETE FROM blacklist WHERE id = $1", server_id)
            return await ctx.send_success(
                f"Unblacklisted server {server_id} from pretend"
            )

    @command(name="reload", aliases=["rl"])
    @is_owner()
    async def reload(self, ctx: PretendContext, *, module: str):
        """
        Reload a module
        """

        reloaded = []
        if module.endswith(" --pull"):
            os.system("git pull")
        module = module.replace(" --pull", "")

        if module == "~":
            for module in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(module)
                except Exception as e:
                    return await ctx.send_warning(
                        f"Couldn't reload **{module}**\n```{e}```"
                    )
                reloaded.append(module)

                return await ctx.send_success(f"Reloaded **{len(reloaded)}** modules")
        else:
            module = module.replace("%", "cogs").replace("!", "tools").strip()
            if module.startswith("cogs"):
                try:
                    await self.bot.reload_extension(module)
                except Exception as e:
                    return await ctx.send_warning(
                        f"Couldn't reload **{module}**\n```{e}```"
                    )
            else:
                try:
                    _module = importlib.import_module(module)
                    importlib.reload(_module)
                except Exception as e:
                    return await ctx.send_warning(
                        f"Couldn't reload **{module}**\n```{e}```"
                    )
            reloaded.append(module)

        await ctx.send_success(
            f"Reloaded **{reloaded[0]}**"
            if len(reloaded) == 1
            else f"Reloaded **{len(reloaded)}** modules"
        )


async def get_sub_type(self, guild):
    auth = await self.bot.db.fetchrow(
        "SELECT * FROM AUTHORIZE WHERE guild_id = $1", guild.id
    )
    if auth:
        till = auth.get("till")
        if till:
            return "monthly"
        else:
            return "onetime"
    else:
        if guild.member_count > 5000:
            return "5k"
        else:
            return "none"


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Owner(bot))
