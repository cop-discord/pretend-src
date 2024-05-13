import asyncio

from discord import Interaction, Embed, Role, PartialEmoji, Member
from discord.ext.commands import Cog, group, has_guild_permissions

from typing import Union

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.converters import HexColor, NewRoleConverter
from tools.predicates import br_is_configured, has_br_role, boosted_to


class Boosterrole(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Manage your personal booster role"

    @Cog.listener("on_guild_role_delete")
    async def br_award_deleted(self, role: Role):
        await self.bot.db.execute("DELETE FROM br_award WHERE role_id = $1", role.id)

    @Cog.listener("on_member_update")
    async def give_br_award(self, before: Member, after: Member):
        if (
            not before.guild.premium_subscriber_role in before.roles
            and before.guild.premium_subscriber_role in after.roles
        ):
            if results := await self.bot.db.fetchval(
                "SELECT role_id FROM br_award WHERE guild_id = $1", before.guild.id
            ):
                roles = [
                    after.guild.get_role(result)
                    for result in results
                    if after.guild.get_role(result).is_assignable()
                ]
                await asyncio.gather(
                    *[
                        after.add_roles(role, reason="Booster role awarded given")
                        for role in roles
                    ]
                )
        elif (
            before.guild.premium_subscriber_role in before.roles
            and not after.guild.premium_subscriber_role in after.roles
        ):
            if results := await self.bot.db.fetchval(
                "SELECT role_id FROM br_award WHERE guild_id = $1", before.guild.id
            ):
                roles = [
                    after.guild.get_role(result)
                    for result in results
                    if after.guild.get_role(result).is_assignable()
                    and after.guild.get_role(result) in after.roles
                ]

                await asyncio.gather(
                    *[
                        after.remove_roles(
                            role, reason="Removing booster awards from this member"
                        )
                        for role in roles
                    ]
                )

    @group(invoke_without_command=True, aliases=["br"])
    async def boosterrole(self, ctx):
        await ctx.create_pages()

    @boosterrole.command(name="setup", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def br_setup(self, ctx: PretendContext):
        """
        Setup the booster role module
        """

        if await self.bot.db.fetchrow(
            "SELECT * FROM booster_module WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_warning("Booster role is **already** configured")

        await self.bot.db.execute(
            "INSERT INTO booster_module (guild_id) VALUES ($1)", ctx.guild.id
        )
        return await ctx.send_success("Configured booster role module")

    @boosterrole.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @br_is_configured()
    async def br_reset(self, ctx: PretendContext):
        """
        Disable the booster role module
        """

        async def yes_callback(interaction: Interaction):
            await self.bot.db.execute(
                "DELETE FROM booster_module WHERE guild_id = $1", ctx.guild.id
            )
            await self.bot.db.execute(
                "DELETE FROM booster_roles WHERE guild_id = $1", ctx.guild.id
            )
            return await interaction.response.edit_message(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {ctx.author.mention}: Booster role module cleared",
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction):
            return await interaction.response.edit_message(
                embed=Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: Cancelling action...",
                ),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to unset the boosterrole module? This action is **IRREVERSIBLE**",
            yes_callback,
            no_callback,
        )

    @boosterrole.group(name="award", invoke_without_command=True)
    async def br_award(self, ctx):
        """
        Give additional roles to members when they boost the server
        """

        return await ctx.create_pages()

    @br_award.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def br_award_add(self, ctx: PretendContext, *, role: NewRoleConverter):
        """
        Add a role to the booster role awards
        """

        if await self.bot.db.fetchrow(
            "SELECT * FROM br_award WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        ):
            return await ctx.send_warning(
                "This role is **already** a booster role award"
            )

        await self.bot.db.execute(
            "INSERT INTO br_award VALUES ($1,$2)", ctx.guild.id, role.id
        )
        return await ctx.send_success(f"Added {role.mention} as a booster role award")

    @br_award.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def br_award_remove(self, ctx: PretendContext, *, role: NewRoleConverter):
        """
        Remove a role from the booster role awards
        """

        if not await self.bot.db.fetchrow(
            "SELECT * FROM br_award WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        ):
            return await ctx.send_warning("This role is **not** a booster role award")

        await self.bot.db.execute(
            "DELETE FROM br_award WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        )
        return await ctx.send_success(
            f"Removed {role.mention} from the booster role awards"
        )

    @br_award.command(name="list")
    async def br_award_list(self, ctx: PretendContext):
        """
        Returns all the booster role awards in this server
        """

        if results := await self.bot.db.fetch(
            "SELECT role_id FROM br_award WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.paginate(
                list(map(lambda result: f"<@&{result['role_id']}>", results)),
                f"Booster awards ({len(results)})",
                {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
            )

        return await ctx.send_error("No booster role awards in this server")

    @boosterrole.command(name="base", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @br_is_configured()
    async def br_base(self, ctx: PretendContext, *, role: Role = None):
        """
        Create the booster roles above the given role
        """

        check = await self.bot.db.fetchrow(
            "SELECT base FROM booster_module WHERE guild_id = $1", ctx.guild.id
        )
        if role is None:
            if check is None:
                return await ctx.send_warning(
                    "Booster role module **base role** isn't set"
                )

            await self.bot.db.execute(
                "UPDATE booster_module SET base = $1 WHERE guild_id = $2",
                None,
                ctx.guild.id,
            )
            return await ctx.send_success("Removed base role")

        await self.bot.db.execute(
            "UPDATE booster_module SET base = $1 WHERE guild_id = $2",
            role.id,
            ctx.guild.id,
        )
        return await ctx.send_success(f"Set {role.mention} as base role")

    @boosterrole.command(name="create", brief="server booster")
    @br_is_configured()
    async def br_create(self, ctx: PretendContext, *, name: str = None):
        """
        Create a booster role
        """

        if not ctx.author.premium_since:
            return await ctx.send_warning(
                "You have to **boost** this server to be able to use this command"
            )

        che = await self.bot.db.fetchval(
            "SELECT base FROM booster_module WHERE guild_id = $1", ctx.guild.id
        )

        if not name:
            name = f"{ctx.author.name}'s role"

        if await self.bot.db.fetchrow(
            "SELECT * FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        ):
            return await ctx.send_warning(f"You already have a booster role")

        ro = ctx.guild.get_role(che)
        role = await ctx.guild.create_role(name=name)
        await role.edit(position=ro.position if ro is not None else 1)
        await ctx.author.add_roles(role)
        await self.bot.db.execute(
            """
      INSERT INTO booster_roles 
      VALUES ($1,$2,$3)
      """,
            ctx.guild.id,
            ctx.author.id,
            role.id,
        )
        await ctx.send_success("Booster role created")

    @boosterrole.command(name="name", brief="server booster")
    @has_br_role()
    async def br_name(self, ctx: PretendContext, *, name: str):
        """
        Edit your booster role name
        """

        if len(name) > 32:
            return await ctx.send_warning(
                "The booster role name cannot have more than **32** characters"
            )

        role = ctx.guild.get_role(
            await self.bot.db.fetchval(
                "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                ctx.author.id,
            )
        )
        if not role:
            return await ctx.send_warning(
                f"Your booster role was deleted\nPlease use `{ctx.clean_prefix}br delete` then `{ctx.clean_prefix}br create`"
            )

        await role.edit(name=name, reason="Edited booster role name")
        await ctx.send_success(f"Edited the booster role name to **{name}**")

    @boosterrole.command(name="color", brief="server booster")
    @has_br_role()
    async def br_color(self, ctx: PretendContext, *, color: HexColor):
        """
        Edit the booster role color
        """

        role = ctx.guild.get_role(
            await self.bot.db.fetchval(
                "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                ctx.author.id,
            )
        )
        if not role:
            return await ctx.send_warning(
                f"Your booster role was deleted\nPlease use `{ctx.clean_prefix}br delete` then `{ctx.clean_prefix}br create`"
            )

        await role.edit(color=color.value, reason="Edited booster role color")
        await ctx.send(
            embed=Embed(
                color=color.value,
                description=f"{ctx.author.mention}: Edited the role's color to `{color.hex}`",
            )
        )

    @boosterrole.command(name="icon", brief="server booster")
    @has_br_role()
    @boosted_to(2)
    async def br_icon(self, ctx: PretendContext, *, emoji: Union[PartialEmoji, str]):
        """
        Edit the booster role icon
        """

        role = ctx.guild.get_role(
            await self.bot.db.fetchval(
                "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                ctx.author.id,
            )
        )
        if not role:
            return await ctx.send_warning(
                f"Your booster role was deleted\nPlease use `{ctx.clean_prefix}br delete` then `{ctx.clean_prefix}br create`"
            )

        await role.edit(
            display_icon=(
                await emoji.read() if isinstance(emoji, PartialEmoji) else emoji
            ),
            reason="Edited the booster role icon",
        )
        return await ctx.send_success(
            f"Booster role icon succesfully changed to **{emoji.name if isinstance(emoji, PartialEmoji) else emoji}**"
        )

    @boosterrole.command(name="delete", brief="server booster")
    @has_br_role()
    async def br_delete(self, ctx: PretendContext):
        """
        Delete your booster role
        """

        role = ctx.guild.get_role(
            await self.bot.db.fetchval(
                "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                ctx.author.id,
            )
        )

        if role:
            await role.delete(reason="Booster role deleted")

        await self.bot.db.execute(
            "DELETE FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        return await ctx.send_success("Booster role deleted")

    @boosterrole.command(name="list")
    async def br_list(self, ctx: PretendContext):
        """
        Returns a list of all booster roles created in this server
        """

        results = await self.bot.db.fetch(
            "SELECT * FROM booster_roles WHERE guild_id = $1", ctx.guild.id
        )
        if len(results) == 0:
            return await ctx.send_error("No **booster roles** found in this server")

        return await ctx.paginate(
            [
                f"<@&{result['role_id']}> owned by <@!{result['user_id']}>"
                for result in results
            ],
            f"Booster Roles ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Boosterrole(bot))
