import json
import re

from discord import (
    Embed,
    Member,
    Attachment,
    Role,
    Interaction,
    TextChannel,
    app_commands,
    Emoji,
    PartialEmoji,
    Message,
)

from discord.ext.commands import (
    Cog,
    command,
    has_guild_permissions,
    BadArgument,
    group,
    hybrid_group,
    bot_has_guild_permissions,
    hybrid_command,
)

from tools.validators import (
    ValidEmoji,
    ValidPermission,
    ValidMessage,
    ValidCommand,
    ValidCog,
)

from tools.converters import NewRoleConverter, HexColor
from tools.predicates import bump_enabled, boosted_to
from tools.helpers import PretendContext, Invoking
from tools.misc.views import confessModal
from tools.bot import Pretend

from typing import Union

from tools.handlers.embedbuilder import EmbedBuilder, EmbedScript
from tools.handlers.embedschema import EmbedBuilding


class Config(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Config commands"

    async def embed_json(self, member: Member, attachment: Attachment):
        if not attachment.filename.endswith(".json"):
            raise BadArgument(
                "Attachment should be a **json** file created from discohook"
            )
        try:
            data = json.loads(await attachment.read())
            message = data["backups"][0]["messages"][0]
            if message["data"].get("content"):
                content = EmbedBuilder().embed_replacement(
                    member, message["data"].get("content")
                )
            else:
                content = None
            embeds = []
            for embed in message["data"]["embeds"]:
                e = json.loads(
                    EmbedBuilder().embed_replacement(
                        member, str(embed).replace("'", '"')
                    )
                )
                embeds.append(Embed.from_dict(e))
                if len(embeds) == 10:
                    break
            return {"content": content, "embeds": embeds}
        except json.JSONDecodeError:
            raise BadArgument(f"Couldnt decode json")

    @command(aliases=["ee"], brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def editembed(
        self, ctx: PretendContext, message: Message, *, code: EmbedScript = None
    ):
        """edit an embed sent by pretend"""
        if message.author.id != self.bot.user.id:
            return await ctx.send_warning(
                f"This is not a message sent by **{self.bot.user}**"
            )

        if code is None:
            if ctx.message.attachments:
                code = await self.embed_json(ctx.author, ctx.message.attachments[0])
            else:
                return await ctx.send_help(ctx.command)

        await message.edit(**code)
        await ctx.send_success(f"Edited message -> {message.jump_url}")

    @command(aliases=["ce"], brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def createembed(self, ctx: PretendContext, *, code: EmbedScript = None):
        """create an embed using an embed code"""
        if code is None:
            if ctx.message.attachments:
                code = await self.embed_json(ctx.author, ctx.message.attachments[0])
            else:
                return await ctx.send_help(ctx.command)

        await ctx.send(**code)

    @command(brief="manage_messages")
    @has_guild_permissions(manage_messages=True)
    async def embedsetup(self, ctx: PretendContext):
        """Create an embed using buttons and return an embed code"""
        embed = Embed(color=self.bot.color, description="Created an embed")
        view = EmbedBuilding(ctx)
        return await ctx.send(embed=embed, view=view)

    @command()
    async def copyembed(self, ctx: PretendContext, message: ValidMessage):
        """copy the embed code of a certain embed"""
        await ctx.send(f"```{EmbedBuilder().copy_embed(message)}```")

    @group(invoke_without_command=True)
    async def usertrack(self, ctx):
        await ctx.create_pages()

    @usertrack.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def usernames_add(self, ctx: PretendContext, *, channel: TextChannel):
        """add a channel for username tracking"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM username_track WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            return await ctx.send_warning(
                "The bot is already tracking usernames for this server"
            )

        webhooks = [w for w in await channel.webhooks() if w.token]
        if len(webhooks) == 0:
            webhook = await channel.create_webhook(name="pretend-usernames")
        else:
            webhook = webhooks[0]

        await self.bot.db.execute(
            "INSERT INTO username_track VALUES ($1,$2)", ctx.guild.id, webhook.url
        )
        return await ctx.send_success(
            f"The bot will start tracking new available usernames in {channel.mention}"
        )

    @usertrack.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def usernames_remove(self, ctx: PretendContext):
        """remove the username tracking from your server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM username_track WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            return await ctx.send_warning(
                "Username tracking is **not** enabled in this server"
            )

        await self.bot.db.execute(
            "DELETE FROM username_track WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success("Disabled username tracking in this server")

    @command(brief="manage server", aliases=["disablecommand"])
    @has_guild_permissions(manage_guild=True)
    async def disablecmd(self, ctx: PretendContext, *, command: ValidCommand):
        """
        disable a command in the server
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM disablecmd WHERE guild_id = $1 AND cmd = $2",
            ctx.guild.id,
            command,
        )

        if check:
            return await ctx.send_error("This command is **already** disabled")

        await self.bot.db.execute(
            "INSERT INTO disablecmd VALUES ($1,$2)", ctx.guild.id, command
        )
        return await ctx.send_success(f"Succesfully disabled **{command}**")

    @command(brief="manage server", aliases=["enablecommand"])
    @has_guild_permissions(manage_guild=True)
    async def enablecmd(self, ctx: PretendContext, *, command: ValidCommand):
        """enable a command in the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM disablecmd WHERE guild_id = $1 AND cmd = $2",
            ctx.guild.id,
            command,
        )

        if not check:
            return await ctx.send_error("This command is **not** disabled")

        await self.bot.db.execute(
            "DELETE FROM disablecmd WHERE guild_id = $1 AND cmd = $2",
            ctx.guild.id,
            command,
        )
        return await ctx.send_success(f"Succesfully enabled **{command}**")

    @group(invoke_without_command=True)
    async def invoke(self, ctx):
        """manage custom punishment responses"""
        await ctx.create_pages()

    @invoke.command(name="variables")
    async def invoke_variables(self, ctx: PretendContext):
        """returns invoke variables"""
        vars = "\n".join(
            [f"{m} - {Invoking(ctx).variables.get(m)}" for m in Invoking(ctx).variables]
        )
        embed = Embed(
            color=self.bot.color, title="Invoke Variables", description=f">>> {vars}"
        )
        return await ctx.reply(embed=embed)

    @invoke.command(name="unban", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_unban(self, ctx: PretendContext, *, code: str):
        """add a custom unban message"""
        await Invoking(ctx).cmd(code)

    @invoke.command(name="ban", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_ban(self, ctx: PretendContext, *, code: str):
        """add a custom ban message"""
        await Invoking(ctx).cmd(code)

    @invoke.command(name="kick", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_kick(self, ctx: PretendContext, *, code: str):
        """add a custom kick message"""
        await Invoking(ctx).cmd(code)

    @invoke.command(name="mute", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_mute(self, ctx: PretendContext, *, code: str):
        """add a custom mute message"""
        await Invoking(ctx).cmd(code)

    @invoke.command(name="unmute", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_unmute(self, ctx: PretendContext, *, code: str):
        """add a custom unmute message"""
        await Invoking(ctx).cmd(code)

    @invoke.command(name="jail", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_jail(self, ctx: PretendContext, *, code: str):
        """add a custom jail message"""
        await Invoking(ctx).cmd(code)

    @invoke.command(name="unjail", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def invoke_unjail(self, ctx: PretendContext, *, code: str):
        """add a custom unjail message"""
        await Invoking(ctx).cmd(code)

    @hybrid_group(invoke_without_command=True)
    async def autorole(self, ctx):
        """assign roles to members on join"""
        await ctx.create_pages()

    @autorole.command(name="add", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def autorole_add(self, ctx: PretendContext, *, role: NewRoleConverter):
        """assign a role to the autorole module"""
        try:
            await self.bot.db.execute(
                "INSERT INTO autorole VALUES ($1,$2)", ctx.guild.id, role.id
            )
            return await ctx.send_success(f"{role.mention} added as autorole")
        except:
            return await ctx.send_warning("This role is **already** an autorole")

    @autorole.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def autorole_remove(self, ctx: PretendContext, *, role: Role):
        """remove a role from the autorole"""
        if not await self.bot.db.fetchrow(
            "SELECT * FROM autorole WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        ):
            return await ctx.send_warning(
                "This role is **not** configured as an autorole"
            )

        await self.bot.db.execute(
            "DELETE FROM autorole WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        )
        return await ctx.send_success(f"{role.mention} removed from autorole list")

    @autorole.command(name="list")
    async def autorole_list(self, ctx: PretendContext):
        """returns a list of autoroles"""
        results = await self.bot.db.fetch(
            "SELECT * FROM autorole WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_error("No autoroles found for this server")

        await ctx.paginate(
            [f"<@&{result['role_id']}> (`{result['role_id']}`)" for result in results],
            f"Autoroles ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @autorole.command(
        name="clear", description="clear the autorole list", brief="manage server"
    )
    @has_guild_permissions(manage_guild=True)
    async def autorole_clear(self, ctx: PretendContext):
        """delete all the roles from the autorole"""

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                "DELETE FROM autorole WHERE guild_id = $1", interaction.guild.id
            )
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    description="Cleared all the autoroles",
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction):
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color, description="Aborting action...."
                ),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to **clear** the autoroles from this server?",
            yes_callback,
            no_callback,
        )

    @group(invoke_without_command=True)
    async def starboard(self, ctx):
        await ctx.create_pages()

    @starboard.command(name="emoji", aliases=["reaction"], brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def starboard_emoji(self, ctx: PretendContext, emoj: ValidEmoji):
        """set the starboard emoji"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", ctx.guild.id
        )
        emoj = str(emoj)
        if not check:
            await self.bot.db.execute(
                "INSERT INTO starboard VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                None,
                emoj,
                1,
            )
        else:
            await self.bot.db.execute(
                "UPDATE starboard SET emoji = $1 WHERE guild_id = $2",
                emoj,
                ctx.guild.id,
            )

        return await ctx.send_success(f"Set starboard emoji to {emoj}")

    @starboard.command(name="count", aliases=["reactions"], brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def starboard_count(self, ctx: PretendContext, count: int):
        """set the minimum number of reactions a message has to have to be on the starboard"""

        if count < 1:
            return await ctx.send_warning("Number cannot be **lower** than **1**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            await self.bot.db.execute(
                "INSERT INTO starboard VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                None,
                None,
                count,
            )
        else:
            await self.bot.db.execute(
                "UPDATE starboard SET count = $1 WHERE guild_id = $2",
                count,
                ctx.guild.id,
            )
        return await ctx.send_success(f"Set starboard count to **{count}**")

    @starboard.command(name="channel", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def starboard_channel(self, ctx: PretendContext, *, channel: TextChannel):
        """set the channel where all the starboard messages go"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            await self.bot.db.execute(
                "INSERT INTO starboard VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                channel.id,
                None,
                1,
            )
        else:
            await self.bot.db.execute(
                "UPDATE starboard SET channel_id = $1 WHERE guild_id = $2",
                channel.id,
                ctx.guild.id,
            )
        return await ctx.send_success(f"Set starboard channel to **{channel.mention}**")

    @starboard.command(
        name="settings",
        aliases=["config", "stats"],
    )
    async def starboard_settings(self, ctx: PretendContext):
        """check the settings for starboard"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", ctx.guild.id
        )

        if not check:
            return await ctx.send_warning("Starboard is **not** configured")

        embed = Embed(color=self.bot.color)
        embed.set_author(name="starboard settings", icon_url=ctx.guild.icon)
        for i in ["count", "emoji"]:
            embed.add_field(name=i.capitalize(), value=check[i])
        embed.add_field(name="Channel", value=f"<#{check['channel_id']}>")

        await ctx.send(embed=embed)

    @starboard.command(
        name="disable",
        aliases=["remove", "delete", "clear"],
        description="disable the starboard module",
        brief="manage server",
    )
    @has_guild_permissions(manage_guild=True)
    async def starboard_disable(self, ctx: PretendContext):
        """disable the starboard module"""

        async def yes_callback(interaction: Interaction) -> None:
            await interaction.client.db.execute(
                "DELETE FROM starboard WHERE guild_id = $1", interaction.guild.id
            )
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Disabled starboard",
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction) -> None:
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.yes_color, description=f"Aborting action.."
                ),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to **disable** starboard", yes_callback, no_callback
        )

    @app_commands.command()
    async def confess(self, interaction: Interaction):
        """anonymously confess your thoughts"""
        re = await self.bot.db.fetchrow(
            "SELECT * FROM confess_mute WHERE guild_id = $1 AND user_id = $2",
            interaction.guild.id,
            interaction.user.id,
        )

        if re:
            await interaction.warn(
                "You are **muted** from sending confessions in this server",
                ephemeral=True,
            )

        check = await self.bot.db.fetchrow(
            "SELECT channel_id FROM confess WHERE guild_id = $1", interaction.guild.id
        )
        if check:
            return await interaction.response.send_modal(confessModal())

        return await interaction.error(
            "Confessions aren't enabled in this server", ephemeral=True
        )

    @hybrid_group(invoke_without_command=True)
    async def confessions(self, ctx):
        await ctx.create_pages()

    @confessions.command(name="mute", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def confessions_mute(self, ctx: PretendContext, *, confession: int):
        """mute a member that sent a specific confession"""
        check = await self.bot.db.fetchrow(
            "SELECT channel_id FROM confess WHERE guild_id = $1", ctx.guild.id
        )

        if check is None:
            return await ctx.send_warning(
                "Confessions aren't **enabled** in this server"
            )

        re = await self.bot.db.fetchrow(
            "SELECT * FROM confess_members WHERE guild_id = $1 AND confession = $2",
            ctx.guild.id,
            confession,
        )

        if re is None:
            return await ctx.send_warning("Couldn't find that confession")

        member_id = re["user_id"]
        r = await self.bot.db.fetchrow(
            "SELECT * FROM confess_mute WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member_id,
        )

        if r:
            return await ctx.send_warning(
                "This **member** is **already** confession muted"
            )

        await self.bot.db.execute(
            "INSERT INTO confess_mute VALUES ($1,$2)", ctx.guild.id, member_id
        )
        return await ctx.send_success(
            f"The author of confession #{confession} is muted"
        )

    @confessions.command(name="unmute", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def connfessions_unmute(self, ctx: PretendContext, *, confession: str):
        check = await self.bot.db.fetchrow(
            "SELECT channel_id FROM confess WHERE guild_id = $1", ctx.guild.id
        )

        if check is None:
            return await ctx.send_warning(
                "Confessions aren't **enabled** in this server"
            )

        if confession == "all":
            await self.bot.db.execute(
                "DELETE FROM confess_mute WHERE guild_id = $1", ctx.guild.id
            )
            return await ctx.send_success("Unmuted **all** confession muted authors")

        num = int(confession)
        re = await self.bot.db.fetchrow(
            "SELECT * FROM confess_members WHERE guild_id = $1 AND confession = $2",
            ctx.guild.id,
            num,
        )

        if re is None:
            return await ctx.send_warning("Couldn't find that confession")

        member_id = re["user_id"]
        r = await self.bot.db.fetchrow(
            "SELECT * FROM confess_mute WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member_id,
        )

        if not r:
            return await ctx.send_warning("This **member** is **not** confession muted")

        await self.bot.db.execute(
            "DELETE FROM confess_mute WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member_id,
        )
        return await ctx.send_success(f"Unmuted the author of confession #{confession}")

    @confessions.command(name="add", brief="manage_guild")
    @has_guild_permissions(manage_guild=True)
    async def confessions_add(self, ctx: PretendContext, *, channel: TextChannel):
        """set the confessions channel"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM confess WHERE guild_id = $1", ctx.guild.id
        )
        if check is not None:
            await self.bot.db.execute(
                "UPDATE confess SET channel_id = $1 WHERE guild_id = $2",
                channel.id,
                ctx.guild.id,
            )
        elif check is None:
            await self.bot.db.execute(
                "INSERT INTO confess VALUES ($1,$2,$3)", ctx.guild.id, channel.id, 0
            )

        return await ctx.send_success(
            f"confession channel set to {channel.mention}".capitalize()
        )

    @confessions.command(name="remove", aliases=["disable"], brief="manage_guild")
    @has_guild_permissions(manage_guild=True)
    async def confessions_remove(self, ctx: PretendContext):
        """disable the confessions module"""
        check = await self.bot.db.fetchrow(
            "SELECT channel_id FROM confess WHERE guild_id = $1", ctx.guild.id
        )

        if check is None:
            return await ctx.send_warning(
                "Confessions aren't **enabled** in this server"
            )

        await self.bot.db.execute(
            "DELETE FROM confess WHERE guild_id = $1", ctx.guild.id
        )
        await self.bot.db.execute(
            "DELETE FROM confess_members WHERE guild_id = $1", ctx.guild.id
        )
        await self.bot.db.execute(
            "DELETE FROM confess_mute WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success("Confessions disabled")

    @confessions.command(name="channel")
    async def confessions_channel(self, ctx: PretendContext):
        """get the confessions channel"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM confess WHERE guild_id = $1", ctx.guild.id
        )

        if check is not None:
            channel = ctx.guild.get_channel(check["channel_id"])
            embed = Embed(
                color=self.bot.color,
                description=f"confession channel: {channel.mention}\nconfessions sent: **{check['confession']}**",
            )
            return await ctx.reply(embed=embed)
        return await ctx.send_warning("Confessions aren't **enabled** in this server")

    @hybrid_command()
    async def selfprefix(self, ctx: PretendContext, prefix: str):
        """set a personal prefix"""
        if prefix in ["none", "remove"]:
            check = await self.bot.db.fetchrow(
                "SELECT prefix FROM selfprefix WHERE user_id = $1", ctx.author.id
            )

            if not check:
                return await ctx.send_warning("You do **not** have any self prefix")

            await self.bot.db.execute(
                "DELETE FROM selfprefix WHERE user_id = $1", ctx.author.id
            )
            return await ctx.send_success("Self prefix removed")
        if len(prefix) > 7:
            raise BadArgument("Prefix is too long!")

        if not prefix:
            return await ctx.send_warning(f"Self prefix is **too short**")

        try:
            await self.bot.db.execute(
                "INSERT INTO selfprefix VALUES ($1,$2)", ctx.author.id, prefix
            )
        except:
            await self.bot.db.execute(
                "UPDATE selfprefix SET prefix = $1 WHERE user_id = $2",
                prefix,
                ctx.author.id,
            )
        finally:
            return await ctx.send_success(
                f"Self prefix now **configured** as `{prefix}`"
            )

    @hybrid_command(brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def prefix(self, ctx: PretendContext, prefix: str):
        """set a guild prefix"""

        if prefix in ["none", "remove"]:
            check = await self.bot.db.fetchrow(
                "SELECT prefix FROM prefixes WHERE guild_id = $1", ctx.guild.id
            )
            if not check:
                return await ctx.send_warning(
                    "This server does **not** have any prefix"
                )

            await self.bot.db.execute(
                "DELETE FROM prefixes WHERE guild_id = $1", ctx.guild.id
            )
            return await ctx.send_success("Guild prefix removed")

        if len(prefix) > 7:
            raise BadArgument("Prefix is too long!")

        res = await self.bot.db.fetchrow(
            "SELECT * FROM prefixes WHERE guild_id = $1", ctx.guild.id
        )
        if not res:
            args = ["INSERT INTO prefixes VALUES ($1,$2)", ctx.guild.id, prefix]
        else:
            args = [
                "UPDATE prefixes SET prefix = $1 WHERE guild_id = $2",
                prefix,
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(f"Guild prefix now **configured** as `{prefix}`")

    @command()
    async def variables(self, ctx: PretendContext):
        """returns the variables for embed building"""
        user_variables = ">>> {user} - shows user full name with discriminator\n{user.name} - shows user's username\n{user.discriminator} - shows user's discriminator\n{user.id} - shows user's id\n{user.mention} - mentions the user\n{user.avatar} - shows user's avatar\n{user.created_at} - shows the user's account creation date\n{user.joined_at} - shows the user's join date"
        guild_variables = ">>> {guild.name} - shows guild's name\n{guild.icon} - shows guild's icon\n{guild.created_at} - shows the date when the server was created\n{guild.count} - shows the member count\n{guild.boost_count} - shows the number of boosts in the server\n{guild.booster_count} - shows the number of boosters in the server\n{guild.vanity} - shows the server's vanity code if any\n{guild.boost_tier} - shows the guild's boost level\n{guild.count.format} - shows the member count in the ordinal format\n{guild.boost_count.format} - shows the boosts count in ordinal format\n{guild.booster_count.format} - shows the boosters count in ordinal format"
        embeds = [
            Embed(color=self.bot.color, title="Embed Variables", description=l)
            for l in [user_variables, guild_variables]
        ]
        await ctx.paginator(embeds)

    @group(invoke_without_command=True, aliases=["fakeperms", "fp"])
    async def fakepermissions(self, ctx):
        return await ctx.create_pages()

    @fakepermissions.command(name="perms")
    async def fp_perms(self, ctx: PretendContext):
        """get every valid permission that can be used for fake permissions"""
        return await ctx.paginate(
            list(map(lambda p: p[0], ctx.author.guild_permissions)), "Valid permissions"
        )

    @fakepermissions.command(name="add", aliases=["append"], brief="administrator")
    @has_guild_permissions(administrator=True)
    async def fp_add(
        self, ctx: PretendContext, role: NewRoleConverter, permission: ValidPermission
    ):
        """add a fake permission to a role"""
        check = await self.bot.db.fetchrow(
            "SELECT perms FROM fake_perms WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        )
        if not check:
            await self.bot.db.execute(
                "INSERT INTO fake_perms VALUES ($1,$2,$3)",
                ctx.guild.id,
                role.id,
                json.dumps([permission]),
            )
        else:
            perms = json.loads(check[0])
            perms.append(permission)
            await self.bot.db.execute(
                "UPDATE fake_perms SET perms = $1 WHERE guild_id = $2 AND role_id = $3",
                json.dumps(perms),
                ctx.guild.id,
                role.id,
            )
        return await ctx.send_success(
            f"Added `{permission}` to the {role.mention}'s fake permissions"
        )

    @fakepermissions.command(name="remove", brief="administrator")
    @has_guild_permissions(administrator=True)
    async def fp_remove(
        self, ctx: PretendContext, role: NewRoleConverter, permission: ValidPermission
    ):
        """remove a permission from the role's fake permissions"""
        check = await self.bot.db.fetchrow(
            "SELECT perms FROM fake_perms WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        )
        if not check:
            return await ctx.send_warning(
                "There are no fake permissions associated with this role"
            )

        perms = json.loads(check[0])

        if len(perms) > 1:
            perms.remove(permission)
            await self.bot.db.execute(
                "UPDATE fake_perms SET perms = $1 WHERE guild_id = $2 AND role_id = $3",
                json.dumps(perms),
                ctx.guild.id,
                role.id,
            )

        else:
            await self.bot.db.execute(
                "DELETE FROM fake_perms WHERE guild_id = $1 AND role_id = $2",
                ctx.guild.id,
                role.id,
            )

        return await ctx.send_success(
            f"Removed `{permission}` from the {role.mention}'s fake permissions"
        )

    @fakepermissions.command(name="list")
    async def fp_list(self, ctx: PretendContext, *, role: Role):
        """returns a list of the fake permissions associated with a specific role"""
        result = await self.bot.db.fetchrow(
            "SELECT perms FROM fake_perms WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        )
        if not result:
            return await ctx.send_warning(
                "There are no fake permissions associated with this role"
            )

        perms = json.loads(result[0])
        await ctx.paginate(
            perms,
            f"Fake permissions ({len(perms)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @group(invoke_without_command=True)
    async def bumpreminder(self, ctx):
        return await ctx.create_pages()

    @bumpreminder.command(name="enable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def bumpreminder_enable(self, ctx: PretendContext):
        """enable the disboard bump reminder feature in your server"""
        check = await self.bot.db.fetchrow(
            "SELECT guild_id FROM bumpreminder WHERE guild_id = $1", ctx.guild.id
        )

        if check:
            return await ctx.send_error("The bump reminder is **already** enabled")

        await self.bot.db.execute(
            "INSERT INTO bumpreminder (guild_id, thankyou, reminder) VALUES ($1,$2,$3)",
            ctx.guild.id,
            "{embed}{color: #181a14}$v{description: <:heheboithumb_up:1188962953014300703> Thank you for bumping the server! I will remind you **in 2 hours** to do it again}$v{content: {user.mention}}",
            "{embed}{color: #181a14}$v{description: 🕰️ Bump the server using `/bump`}$v{content: {user.mention}}",
        )
        return await ctx.send_success("Bump Reminder is now enabled")

    @bumpreminder.command(name="disable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bump_enabled()
    async def bumpreminder_disable(self, ctx: PretendContext):
        """disable the disboard bump reminder feature"""
        await self.bot.db.execute(
            "DELETE FROM bumpreminder WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success("Bump reminder is now disabled")

    @bumpreminder.command(name="thankyou", aliases=["ty"], brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bump_enabled()
    async def bumpreminder_thankyou(
        self,
        ctx: PretendContext,
        *,
        code: str = "{embed}{color: #181a14}$v{description: <:heheboithumb_up:1188962953014300703> Thank you for bumping the server! I will remind you **in 2 hours** to do it again}$v{content: {user.mention}}",
    ):
        """set the message that will be sent after a person bumps the server"""
        await self.bot.db.execute(
            "UPDATE bumpreminder SET thankyou = $1 WHERE guild_id = $2",
            code,
            ctx.guild.id,
        )
        return await ctx.send_success(
            f"Bump reminder thankyou message updated to\n```\n{code}```"
        )

    @bumpreminder.command(name="reminder", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bump_enabled()
    async def bumpreminder_reminder(
        self,
        ctx: PretendContext,
        *,
        code: str = "{embed}{color: #181a14}$v{description: 🕰️ Bump the server using `/bump`}$v{content: {user.mention}}",
    ):
        """set the message that will be sent when bumping is available"""
        await self.bot.db.execute(
            "UPDATE bumpreminder SET reminder = $1 WHERE guild_id = $2",
            code,
            ctx.guild.id,
        )
        return await ctx.send_success(
            f"Bump reminder reminder message updated to\n```\n{code}```"
        )

    @group(name="reactionrole", invoke_without_command=True, aliases=["rr"])
    async def reactionrole(self, ctx: PretendContext):
        await ctx.create_pages()

    @reactionrole.command(
        name="clear",
        description="delete every reaction role in the server",
        brief="manage server",
    )
    @has_guild_permissions(manage_guild=True)
    async def rr_clear(self, ctx: PretendContext):
        """delete every reaction role in the server"""

        async def yes_callback(interaction: Interaction) -> None:
            await interaction.client.db.execute(
                "DELETE FROM reactionrole WHERE guild_id = $1", interaction.guild.id
            )
            return await interaction.response.edit_message(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {interaction.user.mention}: Cleared **all** reaction roles from the server",
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction) -> None:
            return await interaction.response.edit_message(
                embed=Embed(color=self.bot.yes_color, description=f"Aborting action.."),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to clear **all** reaction roles from the server? The reactions won't be removed",
            yes_callback,
            no_callback,
        )

    @reactionrole.command(name="list")
    async def rr_list(self, ctx: PretendContext):
        """returns a list of reaction roles in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM reactionrole WHERE guild_id = $1", ctx.guild.id
        )
        if len(results) == 0:
            return await ctx.send_error("No reaction roles available for this server")

        return await ctx.paginate(
            [
                f"{result['emoji']} <@&{result['role_id']}> [**here**](https://discord.com/channels/{ctx.guild.id}/{result['channel_id']}/{result['message_id']})"
                for result in results
            ],
            f"Reaction Roles ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @reactionrole.command(
        name="remove",
        brief="manage roles",
        usage="example: ;rr remove https://discord.com/channels/1134194462218788977/1134194463238000743/1136758099282231446 :skull:",
    )
    @has_guild_permissions(manage_roles=True)
    async def rr_remove(
        self, ctx: PretendContext, message: ValidMessage, emoji: Union[Emoji, str]
    ):
        """remove a certain reaction role emoji"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            ctx.guild.id,
            message.channel.id,
            message.id,
            str(emoji),
        )
        if not check:
            return await ctx.send_error(
                "No reaction role found for the message provided"
            )

        await self.bot.db.execute(
            "DELETE FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            ctx.guild.id,
            message.channel.id,
            message.id,
            str(emoji),
        )
        await message.remove_reaction(emoji, ctx.guild.me)
        return await ctx.send_success(
            "Removed the reaction role from the message provided"
        )

    @reactionrole.command(
        name="add",
        brief="manage roles",
        usage="example: ;rr add https://discord.com/channels/1134194462218788977/1134194463238000743/1136758099282231446 :skull: dead chat",
    )
    @has_guild_permissions(manage_roles=True)
    async def rr_add(
        self,
        ctx: PretendContext,
        message: ValidMessage,
        emoji: Union[Emoji, str],
        *,
        role: NewRoleConverter,
    ):
        """add a reaction role message to an emoji"""

        check = await self.bot.db.fetchrow(
            "SELECT * FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            ctx.guild.id,
            message.channel.id,
            message.id,
            str(emoji),
        )
        if check:
            return await ctx.send_warning(
                "A similar reaction role is **already** added"
            )

        await self.bot.db.execute(
            "INSERT INTO reactionrole VALUES ($1,$2,$3,$4,$5)",
            ctx.guild.id,
            message.channel.id,
            message.id,
            str(emoji),
            role.id,
        )
        await message.add_reaction(emoji)
        return await ctx.send_success(
            f"Added reaction role [**here**]({message.jump_url})"
        )

    @group(invoke_without_command=True)
    async def editrole(self, ctx):
        return await ctx.create_pages()

    @editrole.command(name="name", brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def editrole_name(
        self, ctx: PretendContext, role: NewRoleConverter, *, name: str
    ):
        """edit a role's name"""
        await role.edit(name=name, reason=f"Role name edited by {ctx.author}")
        return await ctx.send_success(f"Role name edited to **{name}**")

    @editrole.command(name="icon", brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @boosted_to(2)
    async def editrole_icon(
        self,
        ctx: PretendContext,
        role: NewRoleConverter,
        *,
        emoji: Union[PartialEmoji, str],
    ):
        """edit a role's icon"""
        await role.edit(
            display_icon=(
                await emoji.read() if isinstance(emoji, PartialEmoji) else emoji
            ),
            reason=f"Role icon edited by {ctx.author}",
        )
        return await ctx.send_success(
            f"Role icon succesfully changed to **{emoji.name if isinstance(emoji, PartialEmoji) else emoji}**"
        )

    @editrole.command(name="hoist", brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def editrole_hoist(self, ctx: PretendContext, *, role: NewRoleConverter):
        """make a role hoisted or not"""
        await role.edit(
            hoist=not role.hoist, reason=f"Role hoist edited by {ctx.author}"
        )
        return await ctx.send_success(
            f"Role {'is now hoisted' if not role.hoist else 'is not hoisted anymore'}"
        )

    @editrole.command(name="color", aliases=["colour"], brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def editrole_color(
        self, ctx: PretendContext, role: NewRoleConverter, color: HexColor
    ):
        """edit a role's color"""
        await role.edit(color=color.value, reason=f"Color changed by {ctx.author}")
        await ctx.send(
            embed=Embed(
                color=color.value,
                description=f"{ctx.author.mention}: Changed the role's color to `{color.hex}`",
            )
        )

    @group(name="alias", brief="manage server", invoke_without_command=True)
    @has_guild_permissions(manage_guild=True)
    async def alias(self, ctx: PretendContext):
        """
        Manage shortcuts for commands
        """

        await ctx.create_pages()

    @alias.command(name="add", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def alias_add(self, ctx: PretendContext, alias: str, *, command: str):
        """
        Create a shortcut for a command
        """

        _command = self.bot.get_command(command)
        if not _command:
            return await ctx.send_error(f"`{command}` is not a command")

        if self.bot.get_command(alias):
            return await ctx.send_error(f"`{alias}` is already a command")

        if check := await self.bot.db.fetch(
            """
      SELECT alias FROM aliases
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        ):
            if len(check) >= 75:
                return await ctx.send_warning(f"You can only have **75 aliases**")

        await self.bot.db.execute(
            """
      INSERT INTO aliases
      VALUES ($1, $2, $3)
      """,
            ctx.guild.id,
            command,
            alias,
        )
        await ctx.send_success(
            f"Added `{alias}` as an alias for `{_command.qualified_name}`"
        )

    @alias.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def alias_remove(self, ctx: PretendContext, *, alias: str):
        """
        Remove an alias for a command
        """
        if not await self.bot.db.fetchrow(
            """
      SELECT * FROM aliases
      WHERE guild_id = $1
      AND alias = $2
      """,
            ctx.guild.id,
            alias,
        ):
            return await ctx.send_warning(f"`{alias}` is **not** an alias")

        await self.bot.db.execute(
            """
      DELETE FROM aliases
      WHERE guild_id = $1
      AND alias = $2
      """,
            ctx.guild.id,
            alias,
        )
        return await ctx.send_success(f"Removed the **alias** `{alias}`")

    @alias.command(name="list", brief="manage server")
    @has_guild_permissions(manage_guild=True)  # WHY IS GIT LIKE THIS
    async def alias_list(self, ctx: PretendContext):
        """
        Returns all the aliases in the server
        """

        results = await self.bot.db.fetch(
            """
      SELECT * FROM aliases
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )
        if not results:
            return await ctx.send_warning(f"No **aliases** are set")

        await ctx.paginate(
            [
                f"`{result['alias']}` runs the command **{result['command']}**"
                for result in results
            ],
            title=f"Aliases ({len(results)})",
            author={"name": ctx.guild.name, "icon_url": ctx.guild.icon or None},
        )

    @group(
        name="restrictcommand",
        aliases=["restrictcmd", "rc"],
        brief="manage sever",
        invoke_without_command=True,
    )
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand(self, ctx: PretendContext):
        """
        Restrict people without roles from using commands
        """

        await ctx.create_pages()

    @restrictcommand.command(name="add", aliases=["make"], brief="manage sever")
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand_add(
        self, ctx: PretendContext, command: str, *, role: Role
    ):
        """
        Restrict a command to the given role
        """

        command = command.replace(".", "")
        _command = self.bot.get_command(command)
        if not _command:
            return await ctx.send_warning(f"Command `{command}` does not exist")

        if _command.name in ("help", "restrictcommand", "disablecmd", "enablecmd"):
            return await ctx.send("no lol")

        if not await self.bot.db.fetchrow(
            "SELECT * FROM restrictcommand WHERE guild_id = $1 AND command = $2 AND role_id = $3",
            ctx.guild.id,
            _command.qualified_name,
            role.id,
        ):
            await self.bot.db.execute(
                """
        INSERT INTO restrictcommand
        VALUES ($1, $2, $3)
        """,
                ctx.guild.id,
                _command.qualified_name,
                role.id,
            )
        else:
            return await ctx.send_warning(
                f"`{_command.qualified_name}` is **already** restricted to {role.mention}"
            )

        await ctx.send_success(
            f"Allowing members with {role.mention} to use `{_command.qualified_name}`"
        )

    @restrictcommand.command(
        name="remove", aliases=["delete", "del"], brief="manage sever"
    )
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand_remove(
        self, ctx: PretendContext, command: str, *, role: Role
    ):
        """
        Stop allowing a role to use a command
        """

        command = command.replace(".", "")
        _command = self.bot.get_command(command)
        if not _command:
            return await ctx.send_warning(f"Command `{command}` does not exist")

        if await self.bot.db.fetchrow(
            "SELECT * FROM restrictcommand WHERE guild_id = $1 AND command = $2 AND role_id = $3",
            ctx.guild.id,
            _command.qualified_name,
            role.id,
        ):
            await self.bot.db.execute(
                """
        DELETE FROM restrictcommand
        WHERE guild_id = $1
        AND command = $2
        AND role_id = $3
        """,
                ctx.guild.id,
                _command.qualified_name,
                role.id,
            )
        else:
            return await ctx.send_warning(
                f"`{_command.qualified_name}` is **not** restricted to {role.mention}"
            )

        await ctx.send_success(
            f"No longer allowing members with {role.mention} to use `{_command.qualified_name}`"
        )

    @restrictcommand.command(name="list", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand_list(self, ctx: PretendContext):
        """
        Get a list of all restricted commands
        """

        results = await self.bot.db.fetch(
            """
      SELECT * FROM restrictcommand
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning(f"There are **no** restricted commands")

        await ctx.paginate(
            [
                f"**{result['command']}**: {ctx.guild.get_role(result['role_id']).mention}"
                for result in results
            ],
            title=f"Restricted Commands ({len(results)})",
            author={
                "name": ctx.guild.name,
                "icon_url": ctx.guild.icon if ctx.guild.icon else None,
            },
        )

    @group(name="set", brief="manage server", invoke_without_command=True)
    @has_guild_permissions(manage_guild=True)
    async def set(self, ctx: PretendContext):
        """
        Modify your server with pretend
        """

        await ctx.create_pages()

    @set.command(name="name", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_name(self, ctx: PretendContext, *, name: str):
        """
        Change your server's name
        """

        if len(name) > 200:
            return await ctx.send_warning(
                f"Server names can't be over **200 characters**"
            )

        _name = ctx.guild.name
        await ctx.guild.edit(name=name)
        await ctx.send_success(f"Changed **{_name}**'s name")

    @set.command(name="icon", aliases=["picture", "pic"], brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_icon(self, ctx: PretendContext, url: str = None):
        """
        Change your server's icon
        """

        if not url:
            url = await ctx.get_attachment()
            if not url:
                return await ctx.send_help(ctx.command)

            url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The image provided is not an url")

        icon = await self.bot.getbyte(url)
        _icon = icon.read()

        try:
            await ctx.guild.edit(icon=_icon)
        except ValueError:
            return await ctx.send_warning(f"Invalid **media type**")
        await ctx.send_success(f"Set the server icon to [`Attachment`]({url})")

    @set.command(name="banner", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_banner(self, ctx: PretendContext, url: str = None):
        """
        Change your server's banner
        """

        if ctx.guild.premium_tier < 2:
            return await ctx.send_warning(f"You haven't **unlocked** banners")

        if not url:
            url = await ctx.get_attachment()
            if not url:
                return await ctx.send_help(ctx.command)

            url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The attachment provided is not an url")

        banner = await self.bot.getbyte(url)
        _banner = banner.read()

        try:
            await ctx.guild.edit(banner=_banner)
        except ValueError:
            return await ctx.send_warning(f"Invalid **media type**")

    @set.command(name="splash", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_splash(self, ctx: PretendContext, url: str = None):
        """
        Change your server's splash
        """

        if ctx.guild.premium_tier < 1:
            return await ctx.send_warning(f"You haven't **unlocked** splash")

        if not url:
            url = await ctx.get_attachment()
            if not url:
                return await ctx.send_help(ctx.command)

            url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The image provided is not an url")

        icon = await self.bot.getbyte(url)
        _icon = icon.read()

        try:
            await ctx.guild.edit(splash=_icon)
        except ValueError:
            return await ctx.send_warning(f"Invalid **media type**")
        await ctx.send_success(f"Set the server icon to [`Attachment`]({url})")

    @group(
        name="imageonly",
        aliases=["imgonly", "gallery"],
        brief="manage channels",
        invoke_without_command=True,
    )
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def imageonly(self, ctx: PretendContext):
        """
        let members only send images in channels
        """

        await ctx.create_pages()

    @imageonly.command(name="add", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def imageonly_add(self, ctx: PretendContext, *, channel: TextChannel):
        """
        add an image only channel
        """

        if await self.bot.db.fetchrow(
            """
      SELECT * FROM imgonly
      WHERE guild_id = $1
      AND channel_id = $2
      """,
            ctx.guild.id,
            channel.id,
        ):
            return await ctx.send_warning(
                f"{channel.mention} is **already** an image only channel"
            )

        await self.bot.db.execute(
            """
      INSERT INTO imgonly
      VALUES ($1, $2)
      """,
            ctx.guild.id,
            channel.id,
        )
        await ctx.send_success(f"{channel.mention} is now an **image only** channel")

    @imageonly.command(name="remove", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def imageonly_remove(self, ctx: PretendContext, *, channel: TextChannel):
        """
        remove an image only channel
        """

        if not await self.bot.db.fetchrow(
            """
      SELECT * FROM imgonly
      WHERE guild_id = $1
      AND channel_id = $2
      """,
            ctx.guild.id,
            channel.id,
        ):
            return await ctx.send_warning(
                f"{channel.mention} is **not** an image only channel"
            )

        await self.bot.db.execute(
            """
      DELETE FROM imgonly
      WHERE guild_id = $1
      AND channel_id = $2
      """,
            ctx.guild.id,
            channel.id,
        )
        await ctx.send_success(
            f"{channel.mention} is no longer an **image only** channel"
        )

    @imageonly.command(name="list", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def imageonly_list(self, ctx: PretendContext):
        """
        returns a list of all image only channels
        """

        results = await self.bot.db.fetch(
            """
      SELECT * FROM imgonly
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )
        if not results:
            return await ctx.send_warning(f"There are **no** image only channels")

        await ctx.paginate(
            [
                f"{self.bot.get_channel(result['channel_id']).mention}"
                for result in results
            ],
            title=f"Image Only Channels ({len(results)})",
            author={
                "name": ctx.guild.name,
                "icon_url": ctx.guild.icon if ctx.guild.icon else None,
            },
        )

    @group(
        name="disablemodule",
        aliases=["dm", "disablem"],
        brief="manage server",
        invoke_without_command=True,
    )
    @has_guild_permissions(manage_guild=True)
    async def disablemodule(self, ctx: PretendContext):
        """
        disable modules of the bot
        """

        await ctx.create_pages()

    @disablemodule.command(name="add", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def disablemodule_add(self, ctx: PretendContext, *, module: ValidCog):
        """
        add a disabled module
        """

        if await self.bot.db.fetchrow(
            """
      SELECT * FROM disablemodule
      WHERE guild_id = $1
      AND module = $2
      """,
            ctx.guild.id,
            module,
        ):
            return await ctx.send_warning(
                f"The `{module}` module is **already** disabled"
            )

        await self.bot.db.execute(
            """
      INSERT INTO disablemodule
      VALUES ($1, $2)
      """,
            ctx.guild.id,
            module,
        )
        await ctx.send_success(f"Successfully disabled **{module}**")

    @disablemodule.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def disablemodule_remove(self, ctx: PretendContext, *, module: ValidCog):
        """
        remove a disabled module
        """

        if not await self.bot.db.fetchrow(
            """
      SELECT * FROM disablemodule
      WHERE guild_id = $1
      AND module = $2
      """,
            ctx.guild.id,
            module,
        ):
            return await ctx.send_warning(f"The `{module}` module is **not** disabled")

        await self.bot.db.execute(
            """
      DELETE FROM disablemodule
      WHERE guild_id = $1
      AND module = $2
      """,
            ctx.guild.id,
            module,
        )
        await ctx.send_success(f"Successfully enabled **{module}**")

    @disablemodule.command(name="list", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def disablemodule_list(self, ctx: PretendContext):
        """
        returns a list of all disabled modules
        """

        results = await self.bot.db.fetch(
            """
      SELECT * FROM disablemodule
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning(f"There are **no** disabled modules")

        await ctx.paginate(
            [f"**{result['module']}**" for result in results],
            title=f"Disabled Modules ({len(results)})",
            author={"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Config(bot))
