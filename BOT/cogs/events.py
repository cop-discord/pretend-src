from discord import Embed, TextChannel, Message, abc, Interaction
from discord.ext.commands import Cog, group, has_guild_permissions, BadArgument

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.predicates import query_limit


class Events(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Event messages commands"

    async def test_message(self, ctx: PretendContext, channel: TextChannel) -> Message:
        table = ctx.command.qualified_name.split(" ")[0]
        check = await self.bot.db.fetchrow(
            f"SELECT * FROM {table} WHERE channel_id = $1", channel.id
        )
        if not check:
            raise BadArgument(f"There is no {table} message in this channel")

        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages or not perms.embed_links:
            raise BadArgument(
                f"I do not have permissions to send the {table} message in {channel.mention}"
            )

        x = await self.bot.embed_build.convert(ctx, check["message"])
        mes = await channel.send(**x)
        return await ctx.send_success(f"Sent the message {mes.jump_url}")

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: abc.GuildChannel):
        if channel.type.name == "text":
            for q in ["welcome", "boost", "leave"]:
                await self.bot.db.execute(
                    f"DELETE FROM {q} WHERE channel_id = $1", channel.id
                )

    @group(invoke_without_command=True, aliases=["greet", "wlc", "welc"])
    async def welcome(self, ctx: PretendContext):
        return await ctx.create_pages()

    @welcome.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @query_limit("welcome")
    async def welcome_add(
        self, ctx: PretendContext, channel: TextChannel, *, code: str
    ):
        """add a welcome message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM welcome WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE welcome SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO welcome VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added welcome message to {channel.mention}\n```{code}```"
        )

    @welcome.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_remove(self, ctx: PretendContext, *, channel: TextChannel):
        """remove a welcome message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM welcome WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no welcome message configured in this channel"
            )

        await self.bot.db.execute(
            "DELETE FROM welcome WHERE channel_id = $1", channel.id
        )
        return await ctx.send_success(
            f"Deleted the welcome message from {channel.mention}"
        )

    @welcome.command(name="config", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_config(self, ctx: PretendContext):
        """view any welcome message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM welcome WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no welcome message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"{ctx.guild.get_channel(result['channel_id']).mention}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @welcome.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_test(self, ctx: PretendContext, *, channel: TextChannel):
        """test the welcome message in a channel"""
        await self.test_message(ctx, channel)

    @welcome.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_reset(self, ctx: PretendContext):
        """
        Delete all the welcome messages
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM welcome
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if len(check) == 0:
            return await ctx.send_error(
                "You have **no** welcome messages in this server"
            )

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                """
        DELETE FROM welcome
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )

            embed = Embed(
                color=interaction.client.yes_color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Deleted all welcome messages in this server",
            )

            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(
                color=interaction.client.color, description=f"Action canceled..."
            )

            await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation_send(
            "Are you sure you want to **RESET** all welcome messages in this server?",
            yes_callback,
            no_callback,
        )

    @group(invoke_without_command=True)
    async def leave(self, ctx: PretendContext):
        return await ctx.create_pages()

    @leave.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @query_limit("leave")
    async def leave_add(self, ctx: PretendContext, channel: TextChannel, *, code: str):
        """add a leave message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM leave WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE leave SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO leave VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added leave message to {channel.mention}\n```{code}```"
        )

    @leave.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_remove(self, ctx: PretendContext, *, channel: TextChannel):
        """remove a leave message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM leave WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no leave message configured in this channel"
            )

        await self.bot.db.execute("DELETE FROM leave WHERE channel_id = $1", channel.id)
        return await ctx.send_success(
            f"Deleted the leave message from {channel.mention}"
        )

    @leave.command(name="config", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_config(self, ctx: PretendContext):
        """view any leave message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM leave WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no leave message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @leave.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_test(self, ctx: PretendContext, *, channel: TextChannel):
        """test the leave message in a channel"""
        await self.test_message(ctx, channel)

    @leave.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_reset(self, ctx: PretendContext):
        """
        Delete all the leave messages
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM leave
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if len(check) == 0:
            return await ctx.send_error("You have **no** leave messages in this server")

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                """
        DELETE FROM leave
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )

            embed = Embed(
                color=interaction.client.yes_color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Deleted all leave messages in this server",
            )

            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(
                color=interaction.client.color, description=f"Action canceled..."
            )

            await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation_send(
            "Are you sure you want to **RESET** all leave messages in this server?",
            yes_callback,
            no_callback,
        )

    @group(
        invoke_without_command=True,
    )
    async def boost(self, ctx: PretendContext):
        return await ctx.create_pages()

    @boost.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @query_limit("boost")
    async def boost_add(self, ctx: PretendContext, channel: TextChannel, *, code: str):
        """add a boost message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM boost WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE boost SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO boost VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added boost message to {channel.mention}\n```{code}```"
        )

    @boost.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_remove(self, ctx: PretendContext, *, channel: TextChannel):
        """remove a boost message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM boost WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no boost message configured in this channel"
            )

        await self.bot.db.execute("DELETE FROM boost WHERE channel_id = $1", channel.id)
        return await ctx.send_success(
            f"Deleted the boost message from {channel.mention}"
        )

    @boost.command(name="config", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_config(self, ctx: PretendContext):
        """view any boost message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM boost WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no boost message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @boost.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_test(self, ctx: PretendContext, *, channel: TextChannel):
        """test the boost message in a channel"""
        await self.test_message(ctx, channel)

    @boost.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_reset(self, ctx: PretendContext):
        """
        Delete all the boost messages
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM boost
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if len(check) == 0:
            return await ctx.send_error("You have **no** boost messages in this server")

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                """
        DELETE FROM boost
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )

            embed = Embed(
                color=interaction.client.yes_color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Deleted all boost messages in this server",
            )

            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(
                color=interaction.client.color, description=f"Action canceled..."
            )

            await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation_send(
            "Are you sure you want to **RESET** all boost messages in this server?",
            yes_callback,
            no_callback,
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Events(bot))
