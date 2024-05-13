from discord.abc import GuildChannel
from discord import Embed, PermissionOverwrite
from discord.ext.commands import (
    Cog,
    group,
    has_guild_permissions,
    bot_has_guild_permissions,
    BadArgument,
)

from tools.bot import Pretend
from tools.converters import PretendContext
from tools.converters import ChannelType, CounterMessage, CounterType


class Counters(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Server stats displayed on channels"

    async def create_counter_channel(
        self, ctx: PretendContext, message: str, replace_with: str, channeltype: str
    ) -> GuildChannel:
        overwrites = {ctx.guild.default_role: PermissionOverwrite(connect=False)}
        reason = "creating member counter"
        name = message.replace("{target}", replace_with)
        if channeltype == "stage":
            channel = await ctx.guild.create_stage_channel(
                name=name, overwrites=overwrites, reason=reason
            )
        elif channeltype == "voice":
            channel = await ctx.guild.create_voice_channel(
                name=name, overwrites=overwrites, reason=reason
            )
        elif channeltype == "category":
            channel = await ctx.guild.create_category(name=name, reason=reason)
        else:
            channel = await ctx.guild.create_text_channel(
                name=name,
                reason=reason,
                overwrites={
                    ctx.guild.default_role: PermissionOverwrite(send_messages=False)
                },
            )

        return channel

    @group(invoke_without_command=True, name="counter")
    async def counter(self, ctx):
        await ctx.create_pages()

    @counter.command(name="types")
    async def counter_types(self, ctx: PretendContext):
        """returns the counter types and channel types"""
        embed1 = Embed(color=self.bot.color, title="counter types")
        embed2 = Embed(color=self.bot.color, title="channel types")
        embed1.description = ">>> members - all members from the server (including bots)\nhumans - all members from the server (excluding bots)\nbots - all bots from the server\nboosters - all server boosters\nvoice - all members in the server's voice channels"
        embed2.description = ">>> voice - creates voice channel\nstage - creates stage channel\ntext - creates text channel\ncategory - creates category channel"
        await ctx.paginator([embed1, embed2])

    @counter.command(name="list")
    async def counter_list(self, ctx: PretendContext):
        """returns a list of the active server counters"""
        results = await self.bot.db.fetch(
            "SELECT * FROM counters WHERE guild_id = $1", ctx.guild.id
        )

        if not results:
            return await ctx.send_warning("There are no counters")

        return await ctx.paginate(
            [
                f"{result['module']} -> {ctx.guild.get_channel(int(result['channel_id'])).mention if ctx.guild.get_channel(int(result['channel_id'])) else result['channel_id']}"
                for result in results
            ],
            f"Counters ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @counter.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def counter_remove(self, ctx: PretendContext, countertype: CounterType):
        """remove a counter from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            countertype,
        )

        if not check:
            raise BadArgument(f"There is no **{countertype}** counter in this server")

        channel = ctx.guild.get_channel(int(check["channel_id"]))

        if channel:
            await channel.delete()

        await self.bot.db.execute(
            "DELETE FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            countertype,
        )
        return await ctx.send_success(f"Removed **{countertype}** counter")

    @counter.group(invoke_without_command=True, name="add", brief="manage guild")
    async def counter_add(self, ctx):
        """add a counter to the server"""
        await ctx.create_pages()

    @counter_add.command(name="members", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def counter_add_members(
        self,
        ctx: PretendContext,
        channeltype: ChannelType,
        *,
        message: CounterMessage = "{target}",
    ):
        """add a counter for the member count"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            ctx.command.name,
        )

        if check:
            return await ctx.send_warning(
                f"<#{check['channel_id']}> is already a **member** counter"
            )

        channel = await self.create_counter_channel(
            ctx, message, str(ctx.guild.member_count), channeltype
        )

        await self.bot.db.execute(
            "INSERT INTO counters VALUES ($1,$2,$3,$4,$5)",
            ctx.guild.id,
            channeltype,
            channel.id,
            message,
            ctx.command.name,
        )
        await ctx.send_success(f"Created **member** counter -> {channel.mention}")

    @counter_add.command(name="humans", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def counter_add_humans(
        self,
        ctx: PretendContext,
        channeltype: ChannelType,
        *,
        message: CounterMessage = "{target}",
    ):
        """add a counter for non bots members"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            ctx.command.name,
        )

        if check:
            return await ctx.send_warning(
                f"<#{check['channel_id']}> is already a **humans** counter"
            )

        channel = await self.create_counter_channel(
            ctx,
            message,
            str(len([m for m in ctx.guild.members if not m.bot])),
            channeltype,
        )

        await self.bot.db.execute(
            "INSERT INTO counters VALUES ($1,$2,$3,$4,$5)",
            ctx.guild.id,
            channeltype,
            channel.id,
            message,
            ctx.command.name,
        )
        await ctx.send_success(f"Created **humans** counter -> {channel.mention}")

    @counter_add.command(name="bots", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def counter_add_bots(
        self,
        ctx: PretendContext,
        channeltype: ChannelType,
        *,
        message: CounterMessage = "{target}",
    ):
        """add a counter for bots"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            ctx.command.name,
        )

        if check:
            return await ctx.send_warning(
                f"<#{check['channel_id']}> is already a **bots** counter"
            )

        channel = await self.create_counter_channel(
            ctx, message, str(len([m for m in ctx.guild.members if m.bot])), channeltype
        )

        await self.bot.db.execute(
            "INSERT INTO counters VALUES ($1,$2,$3,$4,$5)",
            ctx.guild.id,
            channeltype,
            channel.id,
            message,
            ctx.command.name,
        )
        await ctx.send_success(f"Created **bots** counter -> {channel.mention}")

    @counter_add.command(name="voice", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def counter_add_voice(
        self,
        ctx: PretendContext,
        channeltype: ChannelType,
        *,
        message: CounterMessage = "{target}",
    ):
        """add a counter for members that are connected to a voice channel"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            ctx.command.name,
        )

        if check:
            return await ctx.send_warning(
                f"<#{check['channel_id']}> is already a **voice** counter"
            )

        channel = await self.create_counter_channel(
            ctx,
            message,
            str(sum(len(c.members) for c in ctx.guild.voice_channels)),
            channeltype,
        )

        await self.bot.db.execute(
            "INSERT INTO counters VALUES ($1,$2,$3,$4,$5)",
            ctx.guild.id,
            channeltype,
            channel.id,
            message,
            ctx.command.name,
        )
        await ctx.send_success(f"Created **voice** counter -> {channel.mention}")

    @counter_add.command(
        name="boosters",
        brief="manage guild",
        usage="example: ;counter add boosters voice {target} boosters",
    )
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def counter_add_boosters(
        self,
        ctx: PretendContext,
        channeltype: ChannelType,
        *,
        message: CounterMessage = "{target}",
    ):
        """add a counter for boosters"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM counters WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            ctx.command.name,
        )

        if check:
            return await ctx.send_warning(
                f"<#{check['channel_id']}> is already a **booster** counter"
            )

        channel = await self.create_counter_channel(
            ctx, message, str(len(ctx.guild.premium_subscribers)), channeltype
        )

        await self.bot.db.execute(
            "INSERT INTO counters VALUES ($1,$2,$3,$4,$5)",
            ctx.guild.id,
            channeltype,
            channel.id,
            message,
            ctx.command.name,
        )
        await ctx.send_success(f"Created **boosters** counter -> {channel.mention}")


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Counters(bot))
