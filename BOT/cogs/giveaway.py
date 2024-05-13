import json
import random
import asyncio
import datetime
import humanfriendly

from tools.bot import Pretend as AB
from tools.predicates import max_gws
from tools.misc.tasks import gwend_task
from tools.helpers import PretendContext
from tools.validators import ValidMessage
from tools.persistent.giveaway import GiveawayView

from discord import Embed, TextChannel
from discord.ext.commands import (
    Cog,
    command,
    has_guild_permissions,
    group,
    CurrentChannel,
)


class Giveaway(Cog):
    def __init__(self, bot: AB):
        self.bot = bot
        self.emoji = "🎉"
        self.description = "Giveaway commands"

    @command(brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def gcreate(
        self, ctx: PretendContext, *, channel: TextChannel = CurrentChannel
    ):
        """create a giveaway in this server"""
        return await ctx.invoke(
            self.bot.get_command("giveaway create"), channel=channel
        )

    @command()
    async def glist(self, ctx: PretendContext):
        """returns a list of active giveaways in the server"""
        return await ctx.invoke(self.bot.get_command("giveaway list"))

    @command(brief="manage_server")
    @has_guild_permissions(manage_guild=True)
    async def gend(self, ctx: PretendContext, message: ValidMessage):
        """end a giveaway"""
        await ctx.invoke(self.bot.get_command("giveaway end"), message=message)

    @command(brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def greroll(self, ctx: PretendContext, message: ValidMessage):
        """reroll a giveaway"""
        await ctx.invoke(self.bot.get_command("giveaway reroll"), message=message)

    @group(invoke_without_command=True, aliases=["gw"])
    async def giveaway(self, ctx):
        """manage giveaways in your server"""
        return await ctx.create_pages()

    @giveaway.command(name="end", brief="manage_server")
    @has_guild_permissions(manage_guild=True)
    async def gw_end(self, ctx: PretendContext, message: ValidMessage):
        """end a giveaway"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM giveaway WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
            ctx.guild.id,
            message.channel.id,
            message.id,
        )
        if not check:
            return await ctx.send_warning(
                "This message is not a  giveaway or it ended if it was one"
            )
        await gwend_task(self.bot, check, datetime.datetime.now())
        return await ctx.send_success(f"Ended giveaway in {message.channel.mention}")

    @giveaway.command(name="reroll", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def gw_reroll(self, ctx: PretendContext, message: ValidMessage):
        """reroll a giveaway"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM gw_ended WHERE channel_id = $1 AND message_id = $2",
            message.channel.id,
            message.id,
        )
        if not check:
            return await ctx.send_warning(
                f"This message is not a giveaway or it didn't end if it is one. Use `{ctx.clean_prefix}gend` to end the giveaway"
            )
        members = json.loads(check["members"])
        await ctx.reply(f"**New winner:** <@!{random.choice(members)}>")

    @giveaway.command(name="list")
    async def gw_list(self, ctx: PretendContext):
        """returns a list of active giveaways in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM giveaway WHERE guild_id = $1", ctx.guild.id
        )
        if len(results) == 0:
            return await ctx.send_error("There are no giveaways")
        return await ctx.paginate(
            [
                f"[**{result['title']}**](https://discord.com/channels/{ctx.guild.id}/{result['channel_id']}/{result['message_id']}) ends <t:{int(result['finish'].timestamp())}:R>"
                for result in results
            ],
            f"Giveaways in {ctx.guild.name}",
        )

    @giveaway.command(name="create", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @max_gws()
    async def gw_create(
        self, ctx: PretendContext, *, channel: TextChannel = CurrentChannel
    ):
        """create a giveaway in this server"""
        await ctx.reply(f"Starting giveaway in {channel.mention}...")
        responses = []

        for me in [
            "What is the prize for this giveaway?",
            "How long should the Giveaway last?",
            "How many winners should this Giveaway have?",
        ]:
            await ctx.send(me)

            try:
                message = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.author.id == ctx.author.id
                    and m.channel.id == ctx.channel.id,
                    timeout=10.0,
                )
                responses.append(message.content)
                await message.add_reaction("👍")
            except asyncio.TimeoutError:
                return await ctx.send(content="You didn't reply in time")
        description = responses[0]

        try:
            seconds = humanfriendly.parse_timespan(responses[1])
        except humanfriendly.InvalidTimespan:
            return await ctx.send(content="Invalid time parsed")

        try:
            winners = int(responses[2])
        except ValueError:
            return await ctx.send(content="Invalid number of winners")

        embed = Embed(
            color=self.bot.color,
            title=description,
            description=f"Ends: <t:{int((datetime.datetime.now() + datetime.timedelta(seconds=seconds)).timestamp())}> (<t:{int((datetime.datetime.now() + datetime.timedelta(seconds=seconds)).timestamp())}:R>)\nHosted by: {ctx.author.mention}\nWinners: **{winners}**",
        )
        embed.add_field(name="Entries", value="0")
        view = GiveawayView()
        await ctx.send(content=f"Giveaway setup completed! Check {channel.mention}")
        mes = await channel.send(embed=embed, view=view)
        await self.bot.db.execute(
            "INSERT INTO giveaway VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            ctx.guild.id,
            channel.id,
            mes.id,
            winners,
            json.dumps([]),
            (datetime.datetime.now() + datetime.timedelta(seconds=seconds)),
            ctx.author.id,
            description,
        )


async def setup(bot: AB) -> None:
    await bot.add_cog(Giveaway(bot))
