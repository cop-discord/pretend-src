from discord import Member, User, Forbidden
from discord.ext.commands import Cog, group, has_permissions

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.predicates import whitelist_enabled


class Whitelist(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Manage members joining your server"

    @group(
        name="whitelist",
        aliases=["wl"],
        invoke_without_command=True,
        brief="administrator",
    )
    @has_permissions(administrator=True)
    async def whitelist(self, ctx: PretendContext):
        """
        Manage the whitelist module
        """

        await ctx.create_pages()

    @whitelist.command(name="enable", brief="administrator")
    @has_permissions(administrator=True)
    async def whitelist_enable(self, ctx: PretendContext):
        """
        Turn on the whitelist system
        """

        if await self.bot.db.fetchrow(
            """
            SELECT * FROM whitelist_state
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        ):
            return await ctx.send_warning(f"The whitelist is **already** enabled")

        await self.bot.db.execute(
            """
            INSERT INTO whitelist_state
            VALUES ($1, $2)
            """,
            ctx.guild.id,
            "default",
        )
        await ctx.send_success(f"Enabled the **whitelist**")

    @whitelist.command(name="disable", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_disable(self, ctx: PretendContext):
        """
        Turn off the whitelist system
        """

        await self.bot.db.execute(
            """
            DELETE FROM whitelist_state
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        )
        await ctx.send_success(f"Disabled the **whitelist**")

    @whitelist.command(name="message", aliases=["msg", "dm"], brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_message(self, ctx: PretendContext, *, code: str):
        """
        Change the message sent to users when not in the whitelist
        """

        if code.lower().strip() == "none":
            await self.bot.db.execute(
                """
                UPDATE whitelist_state SET embed = $1
                WHERE guild_id = $2
                """,
                "none",
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Removed your **whitelist** message- users will no longer be notified"
            )
        elif code.lower().strip() == "default":
            await self.bot.db.execute(
                """
                UPDATE whitelist_state SET embed = $1
                WHERE guild_id = $2
                """,
                "default",
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Set your **whitelist** message to the default"
            )
        else:
            await self.bot.db.execute(
                """
                UPDATE whitelist_state SET embed = $1
                WHERE guild_id = $2
                """,
                code,
                ctx.guild.id,
            )
            await ctx.send_success(f"Set your **custom** whitelist message")

    @whitelist.command(name="add", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_add(self, ctx: PretendContext, user: User):
        """
        Add someone to the server whitelist
        """

        if await self.bot.db.fetchrow(
            """
            SELECT * FROM whitelist
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            user.id,
        ):
            return await ctx.send_warning(f"{user.mention} is already **whitelisted**")

        await self.bot.db.execute(
            """
            INSERT INTO whitelist
            VALUES ($1, $2)
            """,
            ctx.guild.id,
            user.id,
        )
        await ctx.send_success(f"Added {user.mention} to the **whitelist**")

    @whitelist.command(name="remove", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_remove(self, ctx: PretendContext, user: Member | User):
        """
        Remove someone from the server whitelist
        """

        if not await self.bot.db.fetchrow(
            """
            SELECT * FROM whitelist
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            user.id,
        ):
            return await ctx.send_warning(f"{user.mention} is not **whitelisted**")

        await self.bot.db.execute(
            """
            DELETE FROM whitelist
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            user.id,
        )

        if isinstance(user, Member):
            try:
                await ctx.guild.kick(
                    user,
                    reason=f"Removed from the whitelist by {ctx.author} ({ctx.author.id})",
                )
                i = True
            except Forbidden:
                i = False

        await ctx.send_success(
            f"Removed {user.mention} from the **whitelist**"
            if i is True
            else f"Removed {user.mention} from the **whitelist** - failed to kick the member"
        )

    @whitelist.command(name="list", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_list(self, ctx: PretendContext):
        """
        View all whitelisted members
        """

        results = await self.bot.db.fetch(
            """
            SELECT * FROM whitelist
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_error(f"No users are **whitelisted**")

        await ctx.paginate(
            [f"{self.bot.get_user(result['user_id']).mention}" for result in results],
            title=f"Whitelist Users ({len(results)})",
            author={"name": ctx.guild.name, "icon_url": ctx.guild.icon.url or None},
        )


async def setup(bot: Pretend):
    await bot.add_cog(Whitelist(bot))
