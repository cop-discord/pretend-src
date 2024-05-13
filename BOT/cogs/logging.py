import discord
import asyncio
import datetime

from io import BytesIO
from discord.ext import commands
from collections import defaultdict
from typing import List, Optional, Union

from tools.helpers import PretendContext as Context


class UserID(discord.ui.Button):
    def __init__(self, id_name: str):
        super().__init__(label=id_name, custom_id="logs:user_id")

    async def callback(self, interaction: discord.Interaction):
        footer = interaction.message.embeds[0].footer.text
        message = (
            footer.split(" | ")[1][len("ID: ") :]
            if footer.find("|") != -1
            else footer[len("ID: ") :]
        )
        return await interaction.response.send_message(message, ephemeral=True)


class UserBan(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Ban", style=discord.ButtonStyle.red, custom_id="logs:ban"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message(
                f"You do not have **permissions** to `ban members` in this server",
                ephemeral=True,
            )

        footer = interaction.message.embeds[0].footer.text
        user_id = int(footer.split(" | ")[1][len("ID: ") :])
        if member := interaction.guild.get_member(user_id):
            await member.ban(
                reason=f"Banned by {interaction.user} from logging message"
            )
            await interaction.response.send_message(
                f"Banned {member.mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Unable to ban `{user_id}` (User is not in this server)",
                ephemeral=True,
            )


class LogsView(discord.ui.View):
    def __init__(self, id_name: str = "User ID"):
        super().__init__(timeout=None)
        self.add_item(UserID(id_name))
        self.add_item(
            discord.ui.Button(
                label="Support Server", url="https://discord.gg/pretendbot"
            )
        )


class Logs(commands.Cog):
    def __init__(self, bot):
        self.locks = defaultdict(asyncio.Lock)
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.author.bot:
            if record := await self.bot.db.fetchval(
                "SELECT messages FROM logging WHERE guild_id = $1", before.guild.id
            ):
                if channel := before.guild.get_channel(record):
                    async with self.locks[before.guild.id]:
                        view = LogsView("Message ID")
                        embed = (
                            discord.Embed(
                                color=self.bot.color,
                                title="Message Edit",
                                timestamp=datetime.datetime.now(),
                                description=f"{before.author} edited a message",
                            )
                            .set_author(
                                name=str(after.author),
                                icon_url=after.author.display_avatar.url,
                            )
                            .add_field(
                                name="Before", value=before.content, inline=False
                            )
                            .add_field(name="After", value=after.content, inline=False)
                            .add_field(
                                name="Channel",
                                value=f"{after.channel.mention} (`{after.channel.id}`)",
                            )
                            .set_footer(text=f"ID: {after.id}")
                        )

                        return await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.author.bot:
            if record := await self.bot.db.fetchval(
                "SELECT messages FROM logging WHERE guild_id = $1", message.guild.id
            ):
                if channel := message.guild.get_channel(record):
                    async with self.locks[message.guild.id]:
                        view = LogsView("Message ID")
                        embed = (
                            discord.Embed(
                                color=self.bot.color,
                                title="Message Delete",
                                description=(
                                    message.content
                                    if message.content != ""
                                    else "No Content"
                                ),
                                timestamp=datetime.datetime.now(),
                            )
                            .set_author(
                                name=str(message.author),
                                icon_url=message.author.display_avatar.url,
                            )
                            .add_field(
                                name="Channel",
                                value=f"{message.channel.mention} (`{message.channel.id}`)",
                            )
                            .set_footer(text=f"ID: {message.id}")
                        )

                        if attachment := next(iter(message.attachments), None):
                            if attachment.filename.endswith(
                                ("jpg", "png", "gif", "jpeg")
                            ):
                                embed.set_image(url=attachment.url)
                            else:
                                return await channel.send(
                                    embed=embed,
                                    view=view,
                                    file=discord.File(
                                        BytesIO(await attachment.read()),
                                        filename=attachment.filename,
                                    ),
                                )

                        if sticker := next(iter(message.stickers), None):
                            embed.set_image(url=sticker.url)
                            if embed.description != "No Content":
                                embed.description = sticker.name

                        return await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if record := await self.bot.db.fetchval(
            "SELECT members FROM logging WHERE guild_id = $1", member.guild.id
        ):
            if channel := member.guild.get_channel(record):
                async with self.locks[member.guild.id]:
                    embed = (
                        discord.Embed(
                            color=self.bot.color,
                            title="Member Left",
                            description=f"{member.mention} left the server",
                            timestamp=datetime.datetime.now(),
                        )
                        .set_author(
                            name=str(member), icon_url=member.display_avatar.url
                        )
                        .add_field(
                            name="Account Created",
                            value=f"{discord.utils.format_dt(member.created_at)} {discord.utils.format_dt(member.created_at, style='R')}",
                            inline=False,
                        )
                        .set_footer(
                            text=f"Members: {member.guild.member_count} | ID: {member.id}"
                        )
                    )
                    view = LogsView()
                    return await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: List[discord.Message]):
        messages = messages[::-1]
        guild = messages[0].guild
        message_channel = messages[0].channel
        if record := await self.bot.db.fetchval(
            "SELECT messages FROM logging WHERE guild_id = $1", guild.id
        ):
            if channel := guild.get_channel(record):
                async with self.locks[guild.id]:
                    view = LogsView("Message ID")
                    text_file = BytesIO()
                    text_file.write(
                        bytes(
                            "\n".join(
                                [
                                    f"[{idx}] {message.author}: {message.clean_content}"
                                    for idx, message in enumerate(messages, start=1)
                                ]
                            ),
                            encoding="utf-8",
                        )
                    )
                    text_file.seek(0)
                    embed = (
                        discord.Embed(
                            color=self.bot.color,
                            title="Bulk Message Delete",
                            description=f"`{len(messages)}` messages got deleted",
                            timestamp=datetime.datetime.now(),
                        )
                        .add_field(
                            name="Channel",
                            value=f"{message_channel.mention} (`{message_channel.id}`)",
                            inline=False,
                        )
                        .set_footer(text=f"ID: {messages[0].id}")
                    )

                    file = discord.File(text_file, filename="messages.txt")

                    return await channel.send(embed=embed, file=file, view=view)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            if record := await self.bot.db.fetchval(
                "SELECT members FROM logging WHERE guild_id = $1", member.guild.id
            ):
                if channel := member.guild.get_channel(record):
                    async with self.locks[member.guild.id]:
                        embed = (
                            discord.Embed(
                                color=self.bot.color,
                                title="Member Join",
                                description=f"{member.mention} joined the server",
                                timestamp=member.joined_at,
                            )
                            .set_author(
                                name=str(member), icon_url=member.display_avatar.url
                            )
                            .add_field(
                                name="Account Created",
                                value=f"{discord.utils.format_dt(member.created_at)} {discord.utils.format_dt(member.created_at, style='R')}",
                                inline=False,
                            )
                            .set_footer(
                                text=f"Members: {member.guild.member_count} | ID: {member.id}"
                            )
                        )
                        view = LogsView()
                        view.add_item(UserBan())
                        return await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if record := await self.bot.db.fetchrow(
            "SELECT * FROM logging WHERE guild_id = $1", entry.guild.id
        ):
            async with self.locks[entry.guild.id]:
                embed = discord.Embed(
                    color=self.bot.color,
                    title=entry.action.name.title().replace("_", " "),
                    timestamp=entry.created_at,
                )

                if entry.action.name.startswith("channel"):
                    id_name = "Channel ID"
                elif entry.action.name.startswith("role"):
                    id_name = "Role ID"
                elif entry.action.name.startswith("guild"):
                    id_name = "Guild ID"
                else:
                    id_name = "User ID"

                view = LogsView(id_name)
                channel: Optional[discord.TextChannel] = None

                match entry.action.name:
                    case "ban":
                        if channel := entry.guild.get_channel(record.members):
                            embed.description = f"<@{entry.target.id}> got banned"
                            embed.set_author(
                                name=str(entry.target),
                                icon_url=(
                                    entry.target.display_avatar.url
                                    if entry.target.display_avatar is not None
                                    else ""
                                ),
                            ).add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Reason", value=entry.reason or "N/A", inline=False
                            ).set_footer(
                                text=f"Members: {entry.guild.member_count} | ID: {entry.target.id}"
                            )
                    case "unban":
                        if channel := entry.guild.get_channel(record.members):
                            embed.description = f"<@{entry.target.id}> got unbanned"
                            embed.set_author(
                                name=str(entry.target),
                                icon_url=(
                                    entry.target.display_avatar.url
                                    if entry.target.display_avatar is not None
                                    else ""
                                ),
                            ).add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Reason", value=entry.reason or "N/A", inline=False
                            ).set_footer(
                                text=f"Members: {entry.guild.member_count} | ID: {entry.target.id}"
                            )
                    case "kick":
                        if channel := entry.guild.get_channel(record.members):
                            embed.description = f"<@{entry.target.id}> got kicked"
                            embed.set_author(
                                name=str(entry.target),
                                icon_url=(
                                    entry.target.display_avatar.url
                                    if entry.target.display_avatar is not None
                                    else ""
                                ),
                            ).add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Reason", value=entry.reason or "N/A", inline=False
                            ).set_footer(
                                text=f"Members: {entry.guild.member_count} | ID: {entry.target.id}"
                            )
                    case "channel_create":
                        if channel := entry.guild.get_channel(record.channels):
                            embed.add_field(
                                name="Channel",
                                value=f"{entry.target.mention} (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Created by",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(
                                text=f"ID: {entry.target.id}"
                            )
                    case "channel_delete":
                        if channel := entry.guild.get_channel(record.channels):
                            embed.add_field(
                                name="Channel",
                                value=f"<#{entry.target.id}> (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Deleted by",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(
                                text=f"ID: {entry.target.id}"
                            )
                    case "channel_update":
                        if channel := entry.guild.get_channel(record.channels):
                            if getattr(entry.before, "name", None) != getattr(
                                entry.after, "name", None
                            ):
                                embed.description = (
                                    f"{entry.target.mention} got a different name"
                                )
                                embed.add_field(
                                    name="Before", value=entry.before.name, inline=False
                                ).add_field(
                                    name="After", value=entry.after.name, inline=False
                                )
                            elif getattr(entry.before, "topic", None) != getattr(
                                entry.after, "topic", None
                            ):
                                embed.description = (
                                    f"{entry.target.mention} got a different topic"
                                )
                                embed.add_field(
                                    name="Before",
                                    value=entry.before.topic,
                                    inline=False,
                                ).add_field(
                                    name="After", value=entry.after.topic, inline=False
                                )
                            elif getattr(entry.before, "nsfw", None) != getattr(
                                entry.after, "nsfw", None
                            ):
                                embed.description = f"{entry.target.mention} {'is now **NSFW**' if entry.after.nsfw else 'is **not NSFW** anymore'}"
                            else:
                                return

                            embed.add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                            ).set_footer(text=f"ID: {entry.target.id}")

                    case "bot_add":
                        if channel := entry.guild.get_channel(record.members):
                            embed.description = (
                                f"{entry.target.mention} was added to this server"
                            )
                            embed.set_author(
                                name=str(entry.target),
                                icon_url=(
                                    entry.target.display_avatar.url
                                    if entry.target.display_avatar is not None
                                    else ""
                                ),
                            ).add_field(
                                name="Bot created",
                                value=f"{discord.utils.format_dt(entry.target.created_at)} {discord.utils.format_dt(entry.target.created_at, style='R')}",
                                inline=False,
                            ).add_field(
                                name="Added by",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(
                                text=f"Members: {entry.guild.member_count} | ID: {entry.target.id}"
                            )
                            view.add_item(UserBan())
                    case "role_create":
                        if channel := entry.guild.get_channel(record.roles):
                            embed.color = (
                                entry.target.color
                                if entry.target.color.value != 0
                                else self.bot.color
                            )
                            embed.add_field(
                                name="Role",
                                value=f"{entry.target.mention} (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Created by",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(
                                text=f"ID: {entry.target.id}"
                            )
                    case "role_delete":
                        if channel := entry.guild.get_channel(record.roles):
                            embed.add_field(
                                name="Role",
                                value=f"<@&{entry.target.id}> (`{entry.target.id}`)",
                                inline=False,
                            ).add_field(
                                name="Deleted by",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(
                                text=f"ID: {entry.target.id}"
                            )
                    case "role_update":
                        if channel := entry.guild.get_channel(record.roles):
                            if getattr(entry.before, "name", None) != getattr(
                                entry.after, "name", None
                            ):
                                embed.description = (
                                    f"{entry.target.mention}'s name got updated"
                                )
                                embed.add_field(
                                    name="Before", value=entry.before.name, inline=False
                                ).add_field(
                                    name="After", value=entry.after.name, inline=False
                                )
                            elif getattr(entry.before, "hoist", None) != getattr(
                                entry.after, "hoist", None
                            ):
                                embed.description = f"{entry.target.mention} {'is **hoisted**' if entry.after.hoist else 'is **not** hoisted anymore'}"
                            elif getattr(entry.before, "mentionable", None) != getattr(
                                entry.after, "mentionable", None
                            ):
                                embed.description = f"{entry.target.mention} {'is **mentionable**' if entry.after.mentionable else 'is **not** mentionable anymore'}"
                            else:
                                return

                            embed.add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(text=f"ID: {entry.target.id}")

                    case "guild_update":
                        if channel := entry.guild.get_channel(record.guild):
                            if getattr(entry.before, "name", None) != getattr(
                                entry.after, "name", None
                            ):
                                embed.description = "Server name updated"
                                embed.add_field(
                                    name=f"Before",
                                    value=entry.before.name,
                                    inline=False,
                                ).add_field(
                                    name="After", value=entry.after.name, inline=False
                                )
                            elif getattr(
                                entry.before, "vanity_url_code", None
                            ) != getattr(entry.after, "vanity_url_code", None):
                                embed.description = "Server vanity updated"
                                embed.add_field(
                                    name="Before",
                                    value=entry.before.vanity_url_code,
                                    inline=False,
                                ).add_field(
                                    name="After",
                                    value=entry.after.vanity_url_code,
                                    inline=False,
                                )
                            elif getattr(entry.before, "owner", None) != getattr(
                                entry.after, "owner", None
                            ):
                                embed.description = f"Server ownership was transfered to **{entry.after.owner}** (`{entry.user.id}`)"
                            else:
                                return

                            embed.set_author(
                                name=str(entry.guild), icon_url=entry.guild.icon
                            ).add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(
                                text=f"ID: {entry.guild.id}"
                            )
                    case "member_role_update":
                        if channel := entry.guild.get_channel(record.members):
                            embed.description = (
                                f"{entry.target.mention}'s roles got updated"
                            )
                            embed.add_field(
                                name="Moderator",
                                value=f"**{entry.user}** (`{entry.user.id}`)",
                                inline=False,
                            ).set_footer(text=f"ID: {entry.target.id}")

                            if entry.changes.after.roles:
                                embed.add_field(
                                    name="Added Roles",
                                    value=(
                                        ", ".join(
                                            [
                                                r.mention
                                                for r in entry.changes.after.roles
                                            ]
                                        )
                                        if len(entry.changes.after.roles) < 6
                                        else ", ".join(
                                            [
                                                r.mention
                                                for r in entry.changes.after.roles[:5]
                                            ]
                                        )
                                        + f" (+ {len(entry.changes.after.roles)-5} more)"
                                    ),
                                    inline=False,
                                )

                            if entry.changes.before.roles:
                                embed.add_field(
                                    name="Removed Roles",
                                    value=(
                                        ", ".join(
                                            [
                                                r.mention
                                                for r in entry.changes.before.roles
                                            ]
                                        )
                                        if len(entry.changes.before.roles) < 6
                                        else ", ".join(
                                            [
                                                r.mention
                                                for r in entry.changes.before.roles[:5]
                                            ]
                                        )
                                        + f" (+ {len(entry.changes.before.roles)-5} more)"
                                    ),
                                    inline=False,
                                )

                            embed.add_field(
                                name="Reason", value=entry.reason or "N/A", inline=False
                            )
                    case _:
                        return

                if channel:
                    return await channel.send(embed=embed, view=view)

    @commands.group(aliases=["logging"], invoke_without_command=True)
    async def logs(self, ctx: Context):
        """
        Log events in your server
        """

        return await ctx.send_help(ctx.command)

    @logs.command(
        name="settings", aliases=["stats", "statistics"], brief="manage server"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_settings(self, ctx: Context):
        """
        Return logs statistics
        """

        if record := await self.bot.db.fetchrow(
            "SELECT * FROM logging WHERE guild_id = $1", ctx.guild.id
        ):
            statistics = [
                f"{category} <#{getattr(record, category)}>"
                for category in ["messages", "roles", "members", "channels", "guild"]
            ]

            if not statistics:
                return await ctx.send_error("Nothing to display")

            embed = discord.Embed(
                color=self.bot.color,
                title=f"Logging stats",
                description="\n".join(statistics),
            ).set_author(name=str(ctx.guild), icon_url=ctx.guild.icon)

            return await ctx.reply(embed=embed)
        return await ctx.send_error("Nothing to display")

    @logs.command(name="messages", aliases=["msgs", "msg"], brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_messages(
        self, ctx: Context, *, channel: Union[discord.TextChannel, str]
    ):
        """
        Log message related events
        """

        if isinstance(channel, str):
            if channel.lower().strip() in ["none", "remove"]:
                if await self.bot.db.fetchval(
                    "SELECT messages FROM logging WHERE guild_id = $1", ctx.guild.id
                ):
                    await self.bot.db.execute(
                        "UPDATE logging SET messages = $1 WHERE guild_id = $2",
                        None,
                        ctx.guild.id,
                    )
                    return await ctx.send_success("No longer logging **messages**")
                else:
                    return await ctx.send_error("Message logging is **not** enabled")
            else:
                raise commands.ChannelNotFound(channel)

        await self.bot.db.execute(
            """
            INSERT INTO logging (guild_id, messages) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET messages = $2
            """,
            ctx.guild.id,
            channel.id,
        )
        return await ctx.send_success(f"Sending **message logs** to {channel.mention}")

    @logs.command(name="guild", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_guild(
        self, ctx: Context, *, channel: Union[discord.TextChannel, str]
    ):
        """
        Log guild related events
        """

        if isinstance(channel, str):
            if channel.lower().strip() in ["none", "remove"]:
                if await self.bot.db.fetchval(
                    "SELECT guild FROM logging WHERE guild_id = $1", ctx.guild.id
                ):
                    await self.bot.db.execute(
                        "UPDATE logging SET guild = $1 WHERE guild_id = $2",
                        None,
                        ctx.guild.id,
                    )
                    return await ctx.send_success("No longer logging **guild events**")
                else:
                    return await ctx.send_error("Guild logging is **not** enabled")
            else:
                raise commands.ChannelNotFound(channel)

        await self.bot.db.execute(
            """
            INSERT INTO logging (guild_id, guild) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET guild = $2
            """,
            ctx.guild.id,
            channel.id,
        )
        return await ctx.send_success(f"Sending **guild logs** to {channel.mention}")

    @logs.command(name="roles", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_roles(
        self, ctx: Context, *, channel: Union[discord.TextChannel, str]
    ):
        """
        Log role related events
        """

        if isinstance(channel, str):
            if channel.lower().strip() in ["none", "remove"]:
                if await self.bot.db.fetchval(
                    "SELECT roles FROM logging WHERE guild_id = $1", ctx.guild.id
                ):
                    await self.bot.db.execute(
                        "UPDATE logging SET roles = $1 WHERE guild_id = $2",
                        None,
                        ctx.guild.id,
                    )
                    return await ctx.send_success("No longer logging **roles**")
                else:
                    return await ctx.send_error("Roles logging is **not** enabled")
            else:
                raise commands.ChannelNotFound(channel)

        await self.bot.db.execute(
            """
            INSERT INTO logging (guild_id, roles) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET roles = $2
            """,
            ctx.guild.id,
            channel.id,
        )
        return await ctx.send_success(f"Sending **role logs** to {channel.mention}")

    @logs.command(name="channels", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_channels(
        self, ctx: Context, *, channel: Union[discord.TextChannel, str]
    ):
        """
        Log channel related events
        """

        if isinstance(channel, str):
            if channel.lower().strip() in ["none", "remove"]:
                if await self.bot.db.fetchval(
                    "SELECT channels FROM logging WHERE guild_id = $1", ctx.guild.id
                ):
                    await self.bot.db.execute(
                        "UPDATE logging SET channels = $1 WHERE guild_id = $2",
                        None,
                        ctx.guild.id,
                    )
                    return await ctx.send_success("No longer logging **channels**")
                else:
                    return await ctx.send_error("Channels logging is **not** enabled")
            else:
                raise commands.ChannelNotFound(channel)

        await self.bot.db.execute(
            """
            INSERT INTO logging (guild_id, channels) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET channels = $2
            """,
            ctx.guild.id,
            channel.id,
        )
        return await ctx.send_success(f"Sending **channel logs** to {channel.mention}")

    @logs.command(name="members", aliases=["mbrs"], brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_members(
        self, ctx: Context, *, channel: Union[discord.TextChannel, str]
    ):
        """
        Log member related events
        """

        if isinstance(channel, str):
            if channel.lower().strip() in ["none", "remove"]:
                if await self.bot.db.fetchval(
                    "SELECT members FROM logging WHERE guild_id = $1", ctx.guild.id
                ):
                    await self.bot.db.execute(
                        "UPDATE logging SET members = $1 WHERE guild_id = $2",
                        None,
                        ctx.guild.id,
                    )
                    return await ctx.send_success("No longer logging **members**")
                else:
                    return await ctx.send_error("Members logging is **not** enabled")
            else:
                raise commands.ChannelNotFound(channel)

        await self.bot.db.execute(
            """
            INSERT INTO logging (guild_id, members) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET members = $2
            """,
            ctx.guild.id,
            channel.id,
        )
        return await ctx.send_success(f"Sending **member logs** to {channel.mention}")


async def setup(bot) -> None:
    return await bot.add_cog(Logs(bot))
