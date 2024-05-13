import re
import json
import asyncio
import datetime

from discord import (
    Member,
    PermissionOverwrite,
    Embed,
    Interaction,
    utils,
    TextChannel,
    User,
    Object,
    Role,
    Forbidden,
    CategoryChannel,
    Message,
    Thread,
    Guild,
)
from discord.ext.commands import (
    Cog,
    hybrid_command,
    has_guild_permissions,
    command,
    group,
    CurrentChannel,
    bot_has_guild_permissions,
    hybrid_group,
)
from discord.abc import GuildChannel

from typing import Union, Optional
from collections import defaultdict
from humanfriendly import format_timespan

from tools.bot import Pretend
from tools.helpers import PretendContext, Invoking
from tools.converters import NoStaff, NewRoleConverter
from tools.validators import ValidTime, ValidNickname, ValidMessage
from tools.predicates import is_jail, admin_antinuke
from tools.misc.views import BoosterMod


class Moderation(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Moderation commands"
        self.locks = defaultdict(asyncio.Lock)
        self.role_lock = defaultdict(asyncio.Lock)

    async def punish_a_bitch(
        self: "Moderation",
        module: str,
        member: Member,
        reason: str,
        role: Optional[Role] = None,
    ):
        """
        Antinuke punish someone

        module [`str`] - the name of the module
        member [`discord.Member`] - the author of the command
        reason [`str`] - the reason of punishment
        role: [`typing.Optional[discord.Role]`] - A role for the role command (can be None)
        """

        if self.bot.an.get_bot_perms(member.guild):
            if await self.bot.an.is_module(module, member.guild):
                if not await self.bot.an.is_whitelisted(member):
                    if not role:
                        if not await self.bot.an.check_threshold(module, member):
                            return

                    if self.bot.an.check_hieracy(member, member.guild.me):
                        cache = self.bot.cache.get(f"{module}-{member.guild.id}")
                        if not cache:
                            await self.bot.cache.set(
                                f"{module}-{member.guild.id}", True, 5
                            )
                            tasks = [
                                await self.bot.an.decide_punishment(
                                    module, member, reason
                                )
                            ]
                            action_time = datetime.datetime.now()
                            check = await self.bot.db.fetchrow(
                                "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                member.guild.id,
                            )
                            await self.bot.an.take_action(
                                reason,
                                member,
                                tasks,
                                action_time,
                                check["owner_id"],
                                member.guild.get_channel(check["logs"]),
                            )

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GuildChannel):
        if check := await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", channel.guild.id
        ):
            if role := channel.guild.get_role(int(check["role_id"])):
                await channel.set_permissions(
                    role,
                    view_channel=False,
                    reason="overwriting permissions for jail role",
                )

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if await self.bot.db.fetchrow(
            "SELECT * FROM jail_members WHERE guild_id = $1 AND user_id = $2",
            member.guild.id,
            member.id,
        ):
            if re := await self.bot.db.fetchrow(
                "SELECT role_id FROM jail WHERE guild_id = $1", member.guild.id
            ):
                if role := member.guild.get_role(re[0]):
                    await member.add_roles(role, reason="member jailed")

    @Cog.listener("on_member_unban")
    async def hardban_check(self, guild: Guild, user: User):
        """
        Listen for hardbans
        """

        if check := await self.bot.db.fetchrow(
            """
    SELECT * FROM hardban
    WHERE guild_id = $1
    AND user_id = $2
    """,
            guild.id,
            user.id,
        ):
            user = self.bot.get_user(check["moderator_id"])
            await guild.ban(
                user,
                reason=f"Hard banned by {user.name} ({user.id}): {check['reason']}",
            )

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        try:
            await self.bot.db.execute(
                """
      INSERT INTO restore
      VALUES ($1,$2,$3)
      """,
                member.guild.id,
                member.id,
                json.dumps([r.id for r in member.roles]),
            )
        except:
            await self.bot.db.execute(
                """
      UPDATE restore
      SET roles = $1
      WHERE guild_id = $2
      AND user_id = $3
      """,
                json.dumps([r.id for r in member.roles]),
                member.guild.id,
                member.id,
            )

    @hybrid_command(brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def restore(self, ctx: PretendContext, *, member: NoStaff):
        """
        give a member their roles back after rejoining
        """

        async with self.locks[ctx.guild.id]:
            check = await self.bot.db.fetchrow(
                """
      SELECT roles FROM restore WHERE guild_id = $1 AND user_id = $2
      """,
                ctx.guild.id,
                member.id,
            )

            if not check:
                return await ctx.send_error("This member doesn't have any roles saved")

            roles = [
                ctx.guild.get_role(r)
                for r in json.loads(check[0])
                if ctx.guild.get_role(r)
            ]
            await member.edit(
                roles=[
                    r
                    for r in roles
                    if r.is_assignable()
                    and not r.position > ctx.author.top_role.position
                ],
                reason=f"roles restored by {ctx.author}",
            )

            await self.bot.db.execute(
                """
      DELETE FROM restore
      WHERE guild_id = $1
      AND user_id = $2
      """,
                ctx.guild.id,
                member.id,
            )
            return await ctx.send_success(f"Restored {member.mention}'s roles")

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    async def setjail(self, ctx: PretendContext):
        """
        Set up jail module
        """

        async with self.locks[ctx.guild.id]:
            if await self.bot.db.fetchrow(
                "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
            ):
                return await ctx.send_warning("Jail is **already** configured")

            mes = await ctx.send_success("Configuring jail..")
            async with ctx.typing():
                role = await ctx.guild.create_role(
                    name="jail", reason="creating jail channel"
                )

                await asyncio.gather(
                    *[
                        channel.set_permissions(role, view_channel=False)
                        for channel in ctx.guild.channels
                    ]
                )

                overwrite = {
                    role: PermissionOverwrite(view_channel=True),
                    ctx.guild.default_role: PermissionOverwrite(view_channel=False),
                }

                text = await ctx.guild.create_text_channel(
                    name="jail-pretend",
                    overwrites=overwrite,
                    reason="creating jail channel",
                )
                await self.bot.db.execute(
                    """
      INSERT INTO jail
      VALUES ($1,$2,$3)
      """,
                    ctx.guild.id,
                    text.id,
                    role.id,
                )

                return await mes.edit(
                    embed=Embed(
                        color=self.bot.yes_color,
                        description=f"{self.bot.yes} {ctx.author.mention}: Jail succesfully configured",
                    )
                )

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @is_jail()
    async def unsetjail(self, ctx: PretendContext):
        """
        disable the jail module
        """

        async def yes_func(interaction: Interaction):
            check = await self.bot.db.fetchrow(
                "SELECT * FROM jail WHERE guild_id = $1", interaction.guild.id
            )
            role = interaction.guild.get_role(check["role_id"])
            channel = interaction.guild.get_channel(check["channel_id"])

            if role:
                await role.delete(reason=f"jail disabled by {ctx.author}")

            if channel:
                await channel.delete(reason=f"jail disabled by {ctx.author}")

            for idk in [
                "DELETE FROM jail WHERE guild_id = $1",
                "DELETE FROM jail_members WHERE guild_id = $1",
            ]:
                await self.bot.db.execute(idk, interaction.guild.id)

            return await interaction.response.edit_message(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {interaction.user.mention}: Disabled the jail module",
                ),
                view=None,
            )

        async def no_func(interaction: Interaction) -> None:
            await interaction.response.edit_message(
                embed=Embed(color=self.bot.color, description="Cancelling action..."),
                view=None,
            )

        return await ctx.confirmation_send(
            f"{ctx.author.mention}: Are you sure you want to **disable** the jail module?\nThis action is **IRREVERSIBLE**",
            yes_func,
            no_func,
        )

    @hybrid_command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_roles=True)
    @is_jail()
    async def jail(
        self,
        ctx: PretendContext,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        Restrict someone from the server's channels
        """

        if await self.bot.db.fetchrow(
            "SELECT * FROM jail_members WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        ):
            return await ctx.send_warning(f"{member.mention} is **already** jailed")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
        )
        role = ctx.guild.get_role(check["role_id"])

        if not role:
            return await ctx.send_error(
                "Jail role **not found**. Please unset jail and set it back"
            )

        old_roles = [r.id for r in member.roles if r.is_assignable()]
        roles = [r for r in member.roles if not r.is_assignable()]
        roles.append(role)
        await member.edit(roles=roles, reason=reason)

        try:
            await member.send(
                f"{member.mention}, you have been jailed in **{ctx.guild.name}** (`{ctx.guild.id}`) - {reason}! Wait for a staff member to unjail you"
            )
        except:
            pass

        await self.bot.db.execute(
            """
    INSERT INTO jail_members VALUES ($1,$2,$3,$4)
    """,
            ctx.guild.id,
            member.id,
            json.dumps(old_roles),
            datetime.datetime.now(),
        )

        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Jailed {member.mention} - {reason}")

    @hybrid_command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_roles=True)
    @is_jail()
    async def unjail(
        self, ctx: PretendContext, member: Member, *, reason: str = "No reason provided"
    ):
        """
        lift the jail restriction from a member
        """

        re = await self.bot.db.fetchrow(
            """
    SELECT roles FROM jail_members
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            member.id,
        )
        if not re:
            return await ctx.send_warning(f"{member.mention} is **not** jailed")

        roles = [
            ctx.guild.get_role(r) for r in json.loads(re[0]) if ctx.guild.get_role(r)
        ]

        if ctx.guild.premium_subscriber_role in member.roles:
            roles.append(ctx.guild.premium_subscriber_role)

        await member.edit(roles=[r for r in roles], reason=reason)
        await self.bot.db.execute(
            """
    DELETE FROM jail_members
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            member.id,
        )

        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Unjailed {member.mention} - {reason}")

    @command()
    async def jailed(self, ctx: PretendContext):
        """
        returns the jailed members
        """

        results = await self.bot.db.fetch(
            "SELECT * FROM jail_members WHERE guild_id = $1", ctx.guild.id
        )
        jailed = [
            f"<@{result['user_id']}> - {utils.format_dt(result['jailed_at'], style='R')}"
            for result in results
            if ctx.guild.get_member(result["user_id"])
        ]

        if len(jailed) > 0:
            return await ctx.paginate(
                jailed,
                f"Jailed members ({len(results)})",
                {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
            )
        else:
            return await ctx.send_warning("There are no jailed members")

    @hybrid_command(brief="mute members")
    @has_guild_permissions(mute_members=True)
    @bot_has_guild_permissions(mute_members=True)
    async def voicemute(self, ctx: PretendContext, *, member: NoStaff):
        """
        Voice mute a member
        """

        if not member.voice:
            return await ctx.send_error("This member is **not** in a voice channel")

        if member.voice.mute:
            return await ctx.send_warning("This member is **already** muted")

        await member.edit(mute=True, reason=f"Member voice muted by {ctx.author}")

        await ctx.send_success(f"Voice muted {member.mention}")

    @hybrid_command(brief="mute members")
    @has_guild_permissions(mute_members=True)
    @bot_has_guild_permissions(mute_members=True)
    async def voiceunmute(self, ctx: PretendContext, *, member: NoStaff):
        """
        Voice unmute a member
        """

        if not member.voice.mute:
            return await ctx.send_warning(f"This member is **not** voice muted")

        await member.edit(mute=False, reason=f"Member voice unmuted by {ctx.author}")

        await ctx.send_success(f"Voice unmuted {member.mention}")

    @hybrid_command(brief="deafen members")
    @has_guild_permissions(deafen_members=True)
    @bot_has_guild_permissions(deafen_members=True)
    async def voicedeafen(self, ctx: PretendContext, *, member: NoStaff):
        """
        Deafen a member in a voice channel
        """

        if not member.voice:
            return await ctx.send_error("This member is **not** in a voice channel")

        if member.voice.deaf:
            return await ctx.send_warning(f"This member is **already** voice deafened")

        await member.edit(deafen=True, reason=f"Member voice deafened by {ctx.author}")

        await ctx.send_success(f"Voice deafened {member.mention}")

    @hybrid_command(brief="deafen members")
    @has_guild_permissions(deafen_members=True)
    @bot_has_guild_permissions(deafen_members=True)
    async def voiceundeafen(self, ctx: PretendContext, *, member: NoStaff):
        """
        Voice undeafen a member
        """

        if not member.voice.deaf:
            return await ctx.send_warning("This member is **not** deafened")

        await member.edit(deafen=False, reason=f"Voice undeafened by {ctx.author}")

        await ctx.send_success(f"Voice undeafened {member.mention}")

    @group(name="clear", invoke_without_command=True)
    async def idk_clear(self, ctx):
        return await ctx.create_pages()

    @idk_clear.command(name="invites", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def clear_invites(self, ctx: PretendContext):
        """
        clear messages that contain discord invite links
        """

        regex = r"discord(?:\.com|app\.com|\.gg)/(?:invite/)?([a-zA-Z0-9\-]{2,32})"
        await ctx.channel.purge(limit=300, check=lambda m: re.search(regex, m.content))

    @idk_clear.command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def contains(self, ctx: PretendContext, *, word: str):
        """
        clear messages that contain a certain word
        """

        await ctx.channel.purge(limit=300, check=lambda m: word in m.content)

    @idk_clear.command(name="images", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def clear_images(self, ctx: PretendContext):
        """
        clear messages that have attachments
        """

        await ctx.channel.purge(limit=300, check=lambda m: m.attachments)

    @command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: PretendContext, number: int, *, member: Member = None):
        """
        delete more messages at once
        """

        async with self.locks[ctx.channel.id]:
            if not member:
                check = lambda m: not m.pinned
            else:
                check = lambda m: m.author.id == member.id and not m.pinned

            await ctx.message.delete()
            await ctx.channel.purge(
                limit=number, check=check, reason=f"Chat purged by {ctx.author}"
            )

    @command(brief="manage messages", aliases=["bc", "bp", "botpurge"])
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def botclear(self, ctx: PretendContext):
        """
        delete messages sent by bots
        """

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=100,
                check=lambda m: m.author.bot and not m.pinned,
                reason=f"Bot messages purged by {ctx.author}",
            )

    @hybrid_group(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: PretendContext, *, channel: TextChannel = CurrentChannel):
        """
        lock a channel
        """

        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            return await ctx.send_error("Channel is **already** locked")

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"channel locked by {ctx.author}",
        )
        return await ctx.send_success(f"Locked {channel.mention}")

    @lock.command(name="all", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def lock_all(
        self, ctx: PretendContext, *, reason: str = "No reason provided"
    ):
        """
        Lock all channels
        """

        async with ctx.channel.typing():
            for channel in ctx.guild.text_channels:
                if (
                    channel.overwrites_for(ctx.guild.default_role).send_messages
                    is False
                ):
                    continue

                if check := await self.bot.db.fetchrow(
                    """
       SELECT role_id FROM lock_role
       WHERE guild_id = $1
       """,
                    ctx.guild.id,
                ):
                    if ctx.guild.get_role(check["role_id"]):
                        role = ctx.guild.get_role(check["role_id"])
                    else:
                        role = ctx.guild.default_role
                else:
                    role = ctx.guild.default_role

                overwrites = channel.overwrites_for(role)
                overwrites.send_messages = False

                await channel.set_permissions(
                    role,
                    overwrite=overwrites,
                    reason=f"{ctx.author} ({ctx.author.id}) locked all channels: {reason}",
                )
                await asyncio.sleep(1.5)

        return await ctx.send_success(f"Locked **all** channels")

    @lock.group(name="ignore", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore(self, ctx: PretendContext):
        """
        Ignore channels from being unlocked when using ;unlock all
        """

        await ctx.create_pages()

    @lock_ignore.command(name="add", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore_add(self, ctx: PretendContext, *, channel: TextChannel):
        """
        Add a channel to be ignored when using ;unlock all
        """

        if await self.bot.db.fetchrow(
            """
    SELECT * FROM lockdown_ignore
    WHERE guild_id = $1
    AND channel_id = $2
    """,
            ctx.guild.id,
            channel.id,
        ):
            return await ctx.send_warning(f"{channel.mention} is **already** ignored")

        await self.bot.db.execute(
            """
    INSERT INTO lockdown_ignore
    VALUES ($1, $2)
    """,
            ctx.guild.id,
            channel.id,
        )
        await ctx.send_success(
            f"Now **ignoring** {channel.mention} from `{ctx.clean_prefix}unlock all`"
        )

    @lock_ignore.command(name="remove", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore_remove(self, ctx: PretendContext, *, channel: TextChannel):
        """
        No longer ignore a channel from unlock all
        """

        if not await self.bot.db.fetchrow(
            """
    SELECT * FROM lockdown_ignore
    WHERE guild_id = $1
    AND channel_id = $2
    """,
            ctx.guild.id,
            channel.id,
        ):
            return await ctx.send_warning(f"{channel.mention} is **not** ignored")

        await self.bot.db.execute(
            """
    DELETE FROM lockdown_ignore
    WHERE guild_id = $1
    AND channel_id = $2
    """,
            ctx.guild.id,
            channel.id,
        )
        await ctx.send_success(f"No longer **ignoring** {channel.mention} from unlock")

    @lock_ignore.command(name="list", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore_list(self, ctx: PretendContext):
        """
        View all ignored unlock channels
        """

        results = await self.bot.db.fetch(
            """
    SELECT * FROM lockdown_ignore
    WHERE guild_id = $1
    """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning(f"There are no ignored unlock channels")

        await ctx.paginate(
            [
                f"{ctx.guild.get_channel(result['channel_id']).mention}"
                for result in results
            ],
            title=f"Ignored Unlock Channels ({len(results)})",
            author={
                "name": ctx.guild.name,
                "icon_url": ctx.guild.icon.url if ctx.guild.icon else None,
            },
        )

    @lock.command(name="role", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def lock_role(self, ctx: PretendContext, role: Role):
        """
        Set the default role for lockdown
        """

        if await self.bot.db.execute(
            "SELECT * FROM lock_role WHERE guild_id = $1", ctx.guild.id
        ):
            args = [
                "UPDATE lock_role SET role_id = $1 WHERE guild_id = $2",
                role.id,
                ctx.guild.id,
            ]
            message = f"Updated the **lock role** to {role.mention}"
        else:
            args = ["INSERT INTO lock_role VALUES ($1, $2)", ctx.guild.id, role.id]
            message = f"Set the **lock role** to {role.mention}"

        await self.bot.db.execute(*args)
        await ctx.send_success(message)

    @hybrid_group(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock(
        self, ctx: PretendContext, *, channel: TextChannel = CurrentChannel
    ):
        """
        unlock a channel
        """

        if (
            channel.overwrites_for(ctx.guild.default_role).send_messages is True
            or channel.overwrites_for(ctx.guild.default_role).send_messages is None
        ):
            return await ctx.send_error("Channel is **already** unlocked")

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"channel unlocked by {ctx.author}",
        )
        return await ctx.send_success(f"Unlocked {channel.mention}")

    @unlock.command(name="all", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock_all(
        self, ctx: PretendContext, *, reason: str = "No reason provided"
    ):
        """
        Unlock all locked channels
        """

        ignored_channels = await self.bot.db.fetch(
            """
    SELECT channel_id FROM lockdown_ignore
    WHERE guild_id = $1
    """,
            ctx.guild.id,
        )

        async with ctx.channel.typing():
            for channel in ctx.guild.text_channels:
                if (
                    channel.overwrites_for(ctx.guild.default_role).send_messages is True
                    or channel.id in ignored_channels
                ):
                    continue

                if check := await self.bot.db.fetchrow(
                    """
       SELECT role_id FROM lock_role
       WHERE guild_id = $1
       """,
                    ctx.guild.id,
                ):
                    if ctx.guild.get_role(check["role_id"]):
                        role = ctx.guild.get_role(check["role_id"])
                    else:
                        role = ctx.guild.default_role
                else:
                    role = ctx.guild.default_role

                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = True
                await channel.set_permissions(
                    role,
                    overwrite=overwrite,
                    reason=f"{ctx.author} ({ctx.author.id}) unlocked all channels: {reason}",
                )

        await ctx.send_success(f"Unlocked all channels")

    @hybrid_command(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def slowmode(
        self,
        ctx: PretendContext,
        time: ValidTime,
        *,
        channel: TextChannel = CurrentChannel,
    ):
        """
        enable slowmode option in a text channel
        """

        await channel.edit(
            slowmode_delay=time, reason=f"Slowmode invoked by {ctx.author}"
        )
        await ctx.send_success(
            f"Slowmode for {channel.mention} set to **{format_timespan(time)}**"
        )

    @hybrid_command(brief="moderate members", aliases=["timeout", "stfu"])
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: PretendContext,
        member: NoStaff,
        time: ValidTime = 3600,
        *,
        reason: str = "No reason provided",
    ):
        """
        timeout a member
        """

        if member.is_timed_out():
            return await ctx.send_error(f"{member.mention} is **already** muted")

        if member.guild_permissions.administrator:
            return await ctx.send_warning("You **cannot** mute an administrator")

        await member.timeout(
            utils.utcnow() + datetime.timedelta(seconds=time), reason=reason
        )

        if not await Invoking(ctx).send(member, reason):
            await ctx.send_success(
                f"Muted {member.mention} for {format_timespan(time)} - **{reason}**"
            )

    @hybrid_command(brief="moderate members", aliases=["untimeout"])
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    async def unmute(
        self,
        ctx: PretendContext,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        Remove the timeout from a member
        """
        if not member.is_timed_out():
            return await ctx.send_error(f"{member.mention} is **not** muted")

        await member.timeout(None, reason=reason)

        if not await Invoking(ctx).send(member, reason):
            await ctx.send_success(f"Unmuted {member.mention} - **{reason}**")

    @hybrid_command(brief="ban members")
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    async def ban(
        self,
        ctx: PretendContext,
        member: Union[Member, User],
        *,
        reason: str = "No reason provided",
    ):
        """
        ban a member from the server
        """

        if isinstance(member, Member):
            member = await NoStaff().convert(ctx, str(member.id))

            if member.premium_since:
                view = BoosterMod(ctx, member, reason)
                embed = Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: Are you sure you want to **ban** {member.mention}? They're boosting this server since **{self.bot.humanize_date(datetime.datetime.fromtimestamp(member.premium_since.timestamp()))}**",
                )
                return await ctx.reply(embed=embed, view=view)

        await ctx.guild.ban(member, reason=reason)
        await self.punish_a_bitch("ban", ctx.author, "Banning Members")
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Banned {member.mention} - **{reason}**")

    @hybrid_command(brief="kick members")
    @has_guild_permissions(kick_members=True)
    @bot_has_guild_permissions(kick_members=True)
    async def kick(
        self,
        ctx: PretendContext,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        kick a member from the server
        """

        if ctx.guild.premium_subscriber_role in member.roles:
            view = BoosterMod(ctx, member, reason)
            embed = Embed(
                color=self.bot.color,
                description=f"{ctx.author.mention}: Are you sure you want to **kick** {member.mention}? They're boosting this server since **{self.bot.humanize_date(datetime.datetime.fromtimestamp(member.premium_since.timestamp()))}**",
            )
            return await ctx.reply(embed=embed, view=view)

        await member.kick(reason=reason)
        await self.punish_a_bitch("ban", ctx.author, "Kicking Members")
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Kicked {member.mention} - **{reason}**")

    @command(brief="ban members")
    @admin_antinuke()
    @bot_has_guild_permissions(ban_members=True)
    async def unbanall(self, ctx: PretendContext):
        """
        unban all members from the server
        """

        async with self.locks[ctx.guild.id]:
            bans = [m.user async for m in ctx.guild.bans()]
            await ctx.pretend_send(f"Unbanning **{len(bans)}** members..")
            await asyncio.gather(*[ctx.guild.unban(Object(m.id)) for m in bans])

    @command(brief="ban members")
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    async def unban(
        self, ctx: PretendContext, member: User, *, reason: str = "No reason provided"
    ):
        """
        unban a member from the server
        """

        if not member.id in [m.user.id async for m in ctx.guild.bans()]:
            return await ctx.send_warning("This member is not banned")

        await ctx.guild.unban(user=member, reason=reason)
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"I unbanned **{member}**")

    @hybrid_command(brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def strip(self, ctx: PretendContext, *, member: NoStaff):
        """
        remove someone's dangerous roles
        """

        roles = [
            role
            for role in member.roles
            if role.is_assignable()
            and not self.bot.is_dangerous(role)
            or role == ctx.guild.premium_subscriber_role
        ]

        await member.edit(roles=roles, reason=f"member stripped by {ctx.author}")
        return await ctx.send_success(f"Stripped {member.mention}'s roles")

    @command(aliases=["nick"], brief="manage nicknames")
    @has_guild_permissions(manage_nicknames=True)
    @bot_has_guild_permissions(manage_nicknames=True)
    async def nickname(
        self, ctx: PretendContext, member: NoStaff, *, nick: ValidNickname
    ):
        """
        change a member's nickname
        """

        await member.edit(nick=nick, reason=f"Nickname changed by {ctx.author}")
        return await ctx.send_success(
            f"Changed {member.mention} nickname to **{nick}**"
            if nick
            else f"Removed {member.mention}'s nickname"
        )

    @group(invoke_without_command=True)
    @has_guild_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: PretendContext,
        member: NoStaff = None,
        *,
        reason: str = "No reason provided",
    ):
        if member is None:
            return await ctx.create_pages()

        date = datetime.datetime.now()
        await self.bot.db.execute(
            """
      INSERT INTO warns
      VALUES ($1,$2,$3,$4,$5)
      """,
            ctx.guild.id,
            member.id,
            ctx.author.id,
            f"{date.day}/{f'0{date.month}' if date.month < 10 else date.month}/{str(date.year)[-2:]} at {datetime.datetime.strptime(f'{date.hour}:{date.minute}', '%H:%M').strftime('%I:%M %p')}",
            reason,
        )
        await ctx.send_success(f"Warned {member.mention} | {reason}")

    @warn.command(name="clear", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def warn_clear(self, ctx: PretendContext, *, member: NoStaff):
        """
        clear all warns from an user
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM warns
      WHERE guild_id = $1
      AND user_id = $2
      """,
            ctx.guild.id,
            member.id,
        )

        if len(check) == 0:
            return await ctx.send_warning("this user has no warnings".capitalize())

        await self.bot.db.execute(
            "DELETE FROM warns WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        )
        await ctx.send_success(f"Removed {member.mention}'s warns")

    @warn.command(name="list")
    @has_guild_permissions(manage_messages=True)
    async def warn_list(self, ctx: PretendContext, *, member: Member):
        """
        returns all warns that an user has
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM warns 
      WHERE guild_id = $1
      AND user_id = $2
      """,
            ctx.guild.id,
            member.id,
        )

        if len(check) == 0:
            return await ctx.send_warning("this user has no warnings".capitalize())

        return await ctx.paginate(
            [
                f"{result['time']} by <@!{result['author_id']}> - {result['reason']}"
                for result in check
            ],
            f"Warnings ({len(check)})",
            {"name": member.name, "icon_url": member.display_avatar.url},
        )

    @command()
    async def warns(self, ctx: PretendContext, *, member: Member):
        """
        shows all warns of an user
        """

        return await ctx.invoke(self.bot.get_command("warn list"), member=member)

    @command(brief="server owner")
    @admin_antinuke()
    @bot_has_guild_permissions(manage_channels=True)
    async def nuke(self, ctx: PretendContext):
        """
        replace the current channel with a new one
        """

        async with self.locks[ctx.channel.id]:

            async def yes_callback(interaction: Interaction) -> None:
                new_channel = await interaction.channel.clone(
                    name=interaction.channel.name,
                    reason="Nuking channel invoked by the server owner",
                )
                message = ""

                await new_channel.edit(
                    topic=interaction.channel.topic,
                    position=interaction.channel.position,
                    nsfw=interaction.channel.nsfw,
                    slowmode_delay=interaction.channel.slowmode_delay,
                    type=interaction.channel.type,
                    reason="Nuking channel invoked by the server owner",
                )

                for i in ["welcome", "leave", "boost"]:
                    if await self.bot.db.fetchrow(
                        f"""
       SELECT * FROM {i}
       WHERE guild_id = $1
       AND channel_id = $2
       """,
                        interaction.guild.id,
                        interaction.channel.id,
                    ):
                        await self.bot.db.execute(
                            f"""
        UPDATE {i}
        SET channel_id = $1
        WHERE guild_id = $2
        AND channel_id = $3
        """,
                            new_channel.id,
                            interaction.guild.id,
                            interaction.channel.id,
                        )
                        message += f" - restored a {i} setup to {new_channel.mention}"

                try:
                    await interaction.channel.delete(
                        reason="Channel nuked by the server owner"
                    )
                except Exception as e:
                    if "community servers" in str(e):
                        return await ctx.send_warning(
                            f"Can't delete channels **required** by community servers"
                        )
                await new_channel.send("💣" + message)

            async def no_callback(interaction: Interaction) -> None:
                await interaction.response.edit_message(
                    embed=Embed(
                        color=self.bot.color, description="Cancelling action..."
                    ),
                    view=None,
                )

            await ctx.confirmation_send(
                f"{ctx.author.mention}: Are you sure you want to **nuke** this channel?\nThis action is **IRREVERSIBLE**",
                yes_callback,
                no_callback,
            )

    @command(brief="manage_roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def roleall(self, ctx: PretendContext, *, role: NewRoleConverter):
        """
        add a role to all members
        """

        async with self.role_lock[ctx.guild.id]:
            tasks = [
                m.add_roles(role, reason=f"Role all invoked by {ctx.author}")
                for m in ctx.guild.members
                if not role in m.roles
            ]

            if len(tasks) == 0:
                return await ctx.send_warning("Everyone has this role")

            mes = await ctx.pretend_send(
                f"Giving {role.mention} to **{len(tasks)}** members. This operation might take around **{format_timespan(0.3*len(tasks))}**"
            )

            await asyncio.gather(*tasks)
            return await mes.edit(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {ctx.author.mention}: Added {role.mention} to **{len(tasks)}** members",
                )
            )

    @command(brief="manage_roles", aliases=["r"])
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def role(self, ctx: PretendContext, member: Member, *, role_string: str):
        """
        Add roles to a member
        """

        roles = [
            await NewRoleConverter().convert(ctx, r) for r in role_string.split(", ")
        ]

        if len(roles) == 0:
            return await ctx.send_help(ctx.command)

        if len(roles) > 7:
            return await ctx.send_error("Too many roles parsed")

        if any(self.bot.is_dangerous(r) for r in roles):
            if await self.bot.an.is_module("role giving", ctx.guild):
                if not await self.bot.an.is_whitelisted(ctx.author):
                    roles = [r for r in roles if not self.bot.is_dangerous(r)]

        if len(roles) > 0:
            async with self.locks[ctx.guild.id]:
                role_mentions = []
                for role in roles:
                    if not role in member.roles:
                        await member.add_roles(
                            role, reason=f"{ctx.author} added the role"
                        )
                        role_mentions.append(f"**+**{role.mention}")
                    else:
                        await member.remove_roles(
                            role, reason=f"{ctx.author} removed the role"
                        )
                        role_mentions.append(f"**-**{role.mention}")

                return await ctx.send_success(
                    f"Edited {member.mention}'s roles: {', '.join(role_mentions)}"
                )
        else:
            return await ctx.send_error("There are no roles that you can give")

    @group(name="channel", brief="manage channels", invoke_without_command=True)
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel(self, ctx: PretendContext):
        """
        Manage channels in your sever
        """

        await ctx.create_pages()

    @channel.command(name="create", aliases=["make"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_create(self, ctx: PretendContext, *, name: str):
        """
        Create a channel in your server
        """

        channel = await ctx.guild.create_text_channel(name=name)
        return await ctx.send_success(f"Created {channel.mention}")

    @channel.command(name="remove", aliases=["delete", "del"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_remove(self, ctx: PretendContext, *, channel: TextChannel):
        """
        Delete a channel in your server
        """

        try:
            await channel.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        except Forbidden:
            return await ctx.send_warning(f"Couldn't delete {channel.mention}")

        await ctx.send_success(f"Deleted channel `#{channel.name}`")

    @channel.command(name="rename", aliases=["name"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_rename(
        self, ctx: PretendContext, channel: TextChannel, *, name: str
    ):
        """
        Rename a channel
        """

        if len(name) > 150:
            return await ctx.send_error(
                f"Channel names can't be over **150 characters**"
            )

        name = name.replace(" ", "-")

        try:
            await channel.edit(name=name)
        except Forbidden:
            return await ctx.send_warning(f"Couldn't rename {channel.mention}")

        await ctx.send_success(f"Renamed `#{channel.name}` to **{name}**")

    @channel.command(name="category", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_category(
        self, ctx: PretendContext, channel: TextChannel, *, category: CategoryChannel
    ):
        """
        Move a channel to a new category
        """

        try:
            await channel.edit(category=category)
        except Forbidden:
            return await ctx.send_warning(
                f"Couldn't change {channel.mention}'s category"
            )

        await ctx.send_success(f"Moved {channel.mention} under {category.mention}")

    @channel.command(name="nsfw", aliases=["naughty"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_nsfw(self, ctx: PretendContext, *, channel: TextChannel):
        """
        Toggle NSFW for a channel
        """

        try:
            await channel.edit(nsfw=not channel.nsfw)
        except Forbidden:
            return await ctx.send_warning(
                f"Couldn't mark/unmark {channel.mention} as NSFW"
            )

        await ctx.message.add_reaction("✅")

    @channel.command(name="topic", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_topic(
        self, ctx: PretendContext, channel: TextChannel, *, topic: str
    ):
        """
        Change a channel's topic
        """

        if len(topic) > 1024:
            return await ctx.send_warning(
                f"Channel topics can't be over **1024 characters**"
            )

        try:
            await channel.edit(topic=topic)
        except Forbidden:
            return await ctx.send_warning(f"Couldn't change {channel.mention}'s topic")

        await ctx.send_success(f"Changed {channel.mention}'s topic to `{topic}`")

    @group(name="category", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category(self, ctx: PretendContext):
        """
        Manage categories in your server
        """

        await ctx.create_pages()

    @category.command(name="create", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category_create(self, ctx: PretendContext, *, name: str):
        """
        Create a category in your server
        """

        category = await ctx.guild.create_category(name=name)

        await ctx.send_success(f"Created category {category.mention}")

    @category.command(name="delete", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category_delete(self, ctx: PretendContext, *, category: CategoryChannel):
        """
        Delete a category in your server
        """

        async def yes_func(interaction: Interaction):
            await category.delete(reason=f"Deleted by {ctx.author} {ctx.author.id}")
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{self.bot.yes} {interaction.user.mention}: Deleted category `#{category.name}`",
                    color=self.bot.yes_color,
                )
            )

        async def no_func(interaction: Interaction):
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{interaction.user.mention}: Cancelling action...",
                    color=self.bot.color,
                )
            )

        await ctx.confirmation_send(
            f"Are you sure you want to **delete** the category `#{category.name}`?",
            yes_func,
            no_func,
        )

    @category.command(name="rename", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category_rename(
        self, ctx: PretendContext, category: CategoryChannel, *, name: str
    ):
        """
        Rename a category in your server
        """

        _name = category.name
        await category.edit(
            name=name, reason=f"Edited by {ctx.author} ({ctx.author.id})"
        )
        await ctx.send_success(f"Renamed **{_name}** to `{name}`")

    @category.command(name="duplicate", aliases=["clone", "remake"])
    @has_guild_permissions(manage_channels=True)
    async def category_duplicate(
        self, ctx: PretendContext, *, category: CategoryChannel
    ):
        """
        Clone an already existing category in your server
        """

        _category = await category.clone(
            name=category.name, reason=f"Cloned by {ctx.author} ({ctx.author.id})"
        )

        await ctx.send_success(f"Cloned {category.mention} to {_category.mention}")

    @command(name="pin", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def pin(self, ctx: PretendContext, message: ValidMessage = None):
        """
        Pin a message
        """

        if not message:
            if ctx.message.reference:
                message = await ctx.fetch_message(int(ctx.message.reference.message_id))
            else:
                async for message in ctx.channel.history(limit=2):
                    message = message

        message: Message = message

        if message.pinned:
            return await ctx.send_warning(f"That message is already **pinned**")

        try:
            await message.pin(reason=f"Pinned by {ctx.author} ({ctx.author.id})")
        except Exception as e:
            if " Cannot execute action on a system message" in str(e):
                return await ctx.send_warning(f"You can't **pin** system messages")

        await ctx.message.add_reaction("✅")

    @command(name="unpin", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def unpin(self, ctx: PretendContext, message: ValidMessage = None):
        """
        Unpin a message
        """

        if not message:
            if ctx.message.reference:
                message = await ctx.fetch_message(int(ctx.message.reference.message_id))
            else:
                async for message in ctx.channel.history(limit=2):
                    message = message

        message: Message = message

        if not message.pinned:
            return await ctx.send_warning(f"That message is **not** pinned")

        await message.unpin(reason=f"Unpinned by {ctx.author} ({ctx.author.id})")
        await ctx.message.add_reaction("✅")

    @group(name="thread", brief="manage threads", invoke_without_command=True)
    @has_guild_permissions(manage_threads=True)
    @bot_has_guild_permissions(manage_threads=True)
    async def thread(self, ctx: PretendContext):
        """
        Manage threads
        """

        await ctx.create_pages()

    @thread.command(name="lock", brief="manage threads")
    @has_guild_permissions(manage_threads=True)
    @bot_has_guild_permissions(manage_threads=True)
    async def thread_lock(self, ctx: PretendContext, thread: Thread = None):
        """
        Lock a thread
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a thread")

        if thread.locked:
            return await ctx.send_warning(f"{thread.mention} is already locked")

        await thread.edit(
            locked=True, reason=f"Locked by {ctx.author} ({ctx.author.id})"
        )
        await ctx.message.add_reaction("✅")

    @thread.command(name="unlock", brief="manage threads")
    @has_guild_permissions(manage_threads=True)
    @bot_has_guild_permissions(manage_threads=True)
    async def thread_unlock(self, ctx: PretendContext, thread: Thread = None):
        """
        Unlock a locked thread
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a thread")

        if not thread.locked:
            return await ctx.send_warning(f"{thread.mention} is **not** locked")

        await thread.edit(
            locked=False, reason=f"Unlocked by {ctx.author} ({ctx.author.id})"
        )
        await ctx.message.add_reaction("✅")

    @command(name="reactionmute", aliases=["rmute"], brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def reactionmute(self, ctx: PretendContext, member: NoStaff):
        """
        Revoke a member's reaction permissions
        """

        member: Member = member

        if ctx.channel.overwrites_for(member).add_reactions is False:
            return await ctx.send_warning(
                f"{member.mention} is **already** reaction muted"
            )

        overwrites = ctx.channel.overwrites_for(member)
        overwrites.add_reactions = False

        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"Reaction permissions removed by {ctx.author} ({ctx.author.id})",
        )
        await ctx.message.add_reaction("✅")

    @command(name="reactionunmute", aliases=["runmute"], brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def reactionunmute(self, ctx: PretendContext, member: NoStaff):
        """
        Grant a reaction muted member reaction permissions
        """

        member: Member = member

        if (
            ctx.channel.overwrites_for(member).add_reactions is True
            or ctx.channel.overwrites_for(member).add_reactions is None
        ):
            return await ctx.send_warning(f"{member.mention} is **not** reaction muted")

        overwrites = ctx.channel.overwrites_for(member)
        overwrites.add_reactions = True

        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"Reaction unmuted by {ctx.author} ({ctx.author.id})",
        )
        await ctx.message.add_reaction("✅")

    @command(name="hardban", brief="administrator & antinuke admin")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(ban_members=True)
    @admin_antinuke()
    async def hardban(
        self,
        ctx: PretendContext,
        member: NoStaff | User,
        *,
        reason: str = "No reason provided",
    ):
        """
        Keep a member banned from the server
        """

        async def yes_callback(interaction: Interaction):
            await self.bot.db.execute(
                """
      INSERT INTO hardban
      VALUES ($1, $2, $3, $4)
      """,
                ctx.guild.id,
                member.id,
                reason,
                ctx.author.id,
            )
            await ctx.guild.ban(
                member, reason=f"Hardbanned by {ctx.author} ({ctx.author.id}): {reason}"
            )
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{self.bot.yes} {interaction.user.mention}: Hardbanned {member.mention}",
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

        await ctx.confirmation_send(
            f"Are you sure you want to **hardban** {member.mention}?",
            yes_callback,
            no_callback,
        )

    @command(name="unhardban", brief="administrator & antinuke admin")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(ban_members=True)
    @admin_antinuke()
    async def unhardban(
        self, ctx: PretendContext, user: User, *, reason: str = "No reason provided"
    ):
        """
        Unhardban a hardbanned member
        """

        check = await self.bot.db.fetchrow(
            """
    SELECT * FROM hardban
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            user.id,
        )

        if not check:
            return await ctx.send_warning(f"{user.mention} is **not** hardbanned")

        if (
            ctx.author.id != ctx.guild.owner.id
            and ctx.author.id != check["moderator_id"]
        ):
            moderator = self.bot.get_user(check["moderator_id"])
            return await ctx.send_warning(
                f"Only {moderator.mention}{f'/{ctx.guild.owner.mention}' if moderator.id != ctx.guild.owner.id else ''} can unhardban {user.mention}"
            )

        await self.bot.db.execute(
            """
    DELETE FROM hardban
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            user.id,
        )

        try:
            await ctx.guild.unban(
                user, reason=f"Unhardbanned by {ctx.author} ({ctx.author.id}): {reason}"
            )
        except:
            pass

        await ctx.send_success(f"Unhardbanned {user.mention}")

    @command(name="revokefiles", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def revokefiles(
        self,
        ctx: PretendContext,
        state: str,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        Remove file attachment permissions from a member
        """

        if not state.lower() in ("on", "off"):
            return await ctx.send_warning(
                f"Invalid state- please provide **on** or **off**"
            )

        if state.lower().strip() == "on":
            overwrite = ctx.channel.overwrites_for(member)
            overwrite.attach_files = False

            await ctx.channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"{ctx.author} ({ctx.author.id}) removed file attachment permissions: {reason}",
            )
        elif state.lower().strip() == "off":
            overwrite = ctx.channel.overwrites_for(member)
            overwrite.attach_files = True

            await ctx.channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"{ctx.author} ({ctx.author.id}) removed file attachment permissions: {reason}",
            )

        await ctx.message.add_reaction("✅")


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Moderation(bot))
