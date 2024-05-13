import asyncio

from discord import Message, Member, Embed, Interaction, TextChannel, Role
from discord.ext.commands import (
    Cog,
    hybrid_group,
    hybrid_command,
    CooldownMapping,
    BucketType,
    Author,
    has_guild_permissions,
)

from typing import Optional
from collections import defaultdict

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.predicates import leveling_enabled
from tools.converters import LevelMember, NewRoleConverter


class Leveling(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Leveling commands"
        self.levelcd = CooldownMapping.from_cooldown(3, 3, BucketType.member)
        self.locks = defaultdict(asyncio.Lock)

    async def level_replace(self, member: Member, params: str):
        """
        replace variables for leveling system
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM level_user WHERE guild_id = $1 AND user_id = $2",
            member.guild.id,
            member.id,
        )
        if "{level}" in params:
            params = params.replace("{level}", str(check["level"]))

        if "{target_xp}" in params:
            params = params.replace("{target_xp}", str(check["target_xp"]))

        return params

    def get_cooldown(self, message: Message) -> Optional[int]:
        """
        this prevents leveling up by spamming
        """

        bucket = self.levelcd.get_bucket(message)
        return bucket.update_rate_limit()

    async def give_rewards(self, member: Member, level: int):
        """
        give the level rewards to users
        """

        results = await self.bot.db.fetch(
            "SELECT role_id FROM level_rewards WHERE guild_id = $1 AND level < $2",
            member.guild.id,
            level + 1,
        )
        if results:
            tasks = [
                member.add_roles(
                    member.guild.get_role(r["role_id"]), reason="Leveled up"
                )
                for r in results
                if not member.guild.get_role(r["role_id"]) in member.roles
                and member.guild.get_role(r["role_id"])
            ]
            await asyncio.gather(*tasks)

    @Cog.listener()
    async def on_message(self, message: Message):
        if not message.author.bot:
            if res := await self.bot.db.fetchrow(
                "SELECT * FROM leveling WHERE guild_id = $1", message.guild.id
            ):
                if not self.get_cooldown(message):
                    async with self.locks[message.author.id]:
                        check = await self.bot.db.fetchrow(
                            """
                SELECT * FROM level_user
                WHERE guild_id = $1
                AND user_id = $2
                """,
                            message.guild.id,
                            message.author.id,
                        )

                        if not check:
                            if res["booster_boost"] and message.author.premium_since:
                                xp = 6
                            else:
                                xp = 4

                            await self.bot.db.execute(
                                """
                    INSERT INTO level_user VALUES ($1,$2,$3,$4,$5)
                    """,
                                message.guild.id,
                                message.author.id,
                                xp,
                                0,
                                int((100 * 1) ** 0.9),
                            )

                            target_xp = 100
                        else:
                            if res["booster_boost"] and message.author.premium_since:
                                xp = check["xp"] + 6
                            else:
                                xp = check["xp"] + 4

                            target_xp = check["target_xp"]

                            await self.bot.db.execute(
                                """
                  UPDATE level_user
                  SET xp = $1
                  WHERE user_id = $2
                  AND guild_id = $3
                  """,
                                xp,
                                message.author.id,
                                message.guild.id,
                            )

                            await self.give_rewards(message.author, check["level"])

                        if xp >= target_xp:
                            level = check["level"] + 1
                            target_xp = int((100 * level + 1) ** 0.9)
                            xp = 0
                            await self.bot.db.execute(
                                """
                  UPDATE level_user
                  SET target_xp = $1,
                  xp = $2,
                  level = $3
                  WHERE user_id = $4
                  AND guild_id = $5
                  """,
                                target_xp,
                                xp,
                                level,
                                message.author.id,
                                message.guild.id,
                            )

                            channel = (
                                message.guild.get_channel(res["channel_id"])
                                or message.channel
                            )
                            mes = res["message"]

                            if mes == "none":
                                return

                            x = await self.bot.embed_build.alt_convert(
                                message.author,
                                await self.level_replace(message.author, mes),
                            )

                            await channel.send(**x)
                            await self.give_rewards(message.author, level)

    @Cog.listener()
    async def on_guild_role_delete(self, role: Role):
        if await self.bot.db.fetchrow(
            "SELECT * FROM level_rewards WHERE guild_id = $1 AND role_id = $2",
            role.guild.id,
            role.id,
        ):
            await self.bot.db.execute(
                "DELETE FROM level_rewards WHERE role_id = $1 AND guild_id = $2",
                role.id,
                role.guild.id,
            )

    @hybrid_command()
    @leveling_enabled()
    async def rank(self, ctx: PretendContext, *, member: Member = Author):
        """
        get the rank of a member
        """

        level = await self.bot.db.fetchrow(
            """
        SELECT * FROM level_user
        WHERE guild_id = $1
        AND user_id = $2
        """,
            ctx.guild.id,
            member.id,
        )
        if not level:
            return await ctx.send_warning("This member doesn't have a rank recorded")

        embed = Embed(color=self.bot.color)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Statistics",
            value=f"Level: `{level['level']}`\nXP: `{level['xp']}`/`{level['target_xp']}`",
        )
        return await ctx.send(embed=embed)

    @hybrid_group(name="level", invoke_without_command=True)
    async def level_cmd(self, ctx: PretendContext, member: Member = Author):
        """
        view the level of a member
        """

        await ctx.invoke(self.bot.get_command("rank"), member=member)

    @level_cmd.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def level_test(self, ctx: PretendContext):
        """
        test your level up message
        """

        res = await self.bot.db.fetchrow(
            """
        SELECT * FROM leveling
        WHERE guild_id = $1
        """,
            ctx.guild.id,
        )
        channel = ctx.guild.get_channel(res["channel_id"]) or ctx.channel
        mes = res["message"]
        x = await self.bot.embed_build.convert(
            ctx, await self.level_replace(ctx.author, mes)
        )
        await channel.send(**x)

    @level_cmd.command(name="enable", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def level_enable(self, ctx: PretendContext):
        """
        enable the leveling system
        """

        if await self.bot.db.fetchrow(
            "SELECT * FROM leveling WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_warning("Leveling system is **already** enabled")

        await self.bot.db.execute(
            """
        INSERT INTO leveling (guild_id, message)
        VALUES ($1,$2)
        """,
            ctx.guild.id,
            "Good job, {user}! You leveled up to **Level {level}**",
        )
        return await ctx.send_success("Enabled the leveling system")

    @level_cmd.command(name="disable", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def level_disable(self, ctx: PretendContext):
        """
        disable the leveling system
        """

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                "DELETE FROM leveling WHERE guild_id = $1", interaction.guild.id
            )
            await interaction.client.db.execute(
                "DELETE FROM level_user WHERE guild_id = $1", interaction.guild.id
            )
            embed = Embed(
                color=interaction.client.color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Disabled the leveling system",
            )
            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(color=self.bot.color, description=f"Aborted the action...")
            await interaction.response.edit_message(embed=embed, view=None)

        await ctx.confirmation_send(
            "Are you sure you want to **reset** the leveling system? This will reset the level statistics aswell",
            yes_callback,
            no_callback,
        )

    @level_cmd.command(name="channel", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def level_channel(
        self, ctx: PretendContext, *, channel: Optional[TextChannel] = None
    ):
        """
        set the level up message destination
        """

        if not channel:
            args = [
                "UPDATE leveling SET channel_id = $1 WHERE guild_id = $2",
                None,
                ctx.guild.id,
            ]
            message = "Level up messages are going to be sent in any channel"
        else:
            args = [
                "Update leveling SET channel_id = $1 WHERE guild_id = $2",
                channel.id,
                ctx.guild.id,
            ]
            message = f"Level up messages are going to be sent in {channel.mention}"

        await self.bot.db.execute(*args)
        await ctx.send_success(message)

    @level_cmd.command(name="variables")
    async def level_variables(self, ctx: PretendContext):
        """
        returns the variables you can use for your custom level message
        """

        embed = Embed(
            color=self.bot.color,
            title="Level Variables",
            description="{level} - The level you reached to\n{target_xp} - The new target xp amount you have to reach",
        )
        await ctx.send(embed=embed)

    @level_cmd.command(name="message", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def level_message(
        self,
        ctx: PretendContext,
        *,
        message: str = "Good job, {user}! You leveled up to **Level {level}**",
    ):
        """
        set a custom level up message
        """

        if message.lower().strip() == "none":
            await self.bot.db.execute(
                """
          UPDATE leveling
          SET message = $1
          WHERE guild_id = $2
          """,
                "none",
                ctx.guild.id,
            )
            return await ctx.send_success(f"Removed the **level up** message")

        await self.bot.db.execute(
            """
        UPDATE leveling
        SET message = $1
        WHERE guild_id = $2
        """,
            message,
            ctx.guild.id,
        )
        return await ctx.send_success(
            f"Level up message configured to:\n```{message}```"
        )

    @level_cmd.group(
        name="multiplier", brief="manage server", invoke_without_command=True
    )
    async def booster_multiplier(self, ctx):
        """
        manage the xp multiplier for boosters
        """

        return await ctx.create_pages()

    @booster_multiplier.command(name="enable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def booster_multiplier_enable(self, ctx: PretendContext):
        """
        enable the multiplier for boosters
        """

        await self.bot.db.execute(
            """
        UPDATE leveling
        SET booster_boost = $1
        WHERE guild_id = $2
        """,
            "yes",
            ctx.guild.id,
        )
        return await ctx.send_success("Enabled multiplier for boosters")

    @booster_multiplier.command(name="disable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def booster_multiplier_disable(self, ctx: PretendContext):
        """
        disable the multiplier for boosters
        """

        await self.bot.db.execute(
            """
        UPDATE leveling
        SET booster_boost = $1
        WHERE guild_id = $2
        """,
            None,
            ctx.guild.id,
        )

        return await ctx.send_success("Disabled multiplier for boosters")

    @level_cmd.command(
        name="config", aliases=["settings", "stats", "statistics", "status"]
    )
    @leveling_enabled()
    async def level_config(self, ctx: PretendContext):
        """
        check the settings for the leveling system
        """

        check = await self.bot.db.fetchrow(
            """
        SELECT * FROM leveling
        WHERE guild_id = $1
        """,
            ctx.guild.id,
        )

        embed = Embed(color=self.bot.color)
        embed.set_author(
            name=f"Level settings for {ctx.guild.name}", icon_url=ctx.guild.icon
        )

        embed.add_field(
            name="Level Channel", value=ctx.guild.get_channel(check["channel_id"])
        )

        embed.add_field(
            name="Booster Multiplier",
            value="enabled" if check["booster_boost"] else "disabled",
        )

        embed.add_field(name="Message", value=check["message"], inline=False)

        await ctx.send(embed=embed)

    @level_cmd.command(name="set", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def level_set(self, ctx: PretendContext, member: LevelMember, level: int):
        """
        set a level to a member
        """

        if level < 1:
            return await ctx.send_error("The level cannot be **lower** than 0")

        if await self.bot.db.fetchrow(
            "SELECT * FROM level_user WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        ):
            await self.bot.db.execute(
                """
          UPDATE level_user
          SET xp = $1,
          target_xp = $2,
          level = $3
          WHERE guild_id = $4
          AND user_id = $5
          """,
                0,
                int((100 * level + 1) ** 0.9),
                level,
                ctx.guild.id,
                member.id,
            )
        else:
            await self.bot.db.execute(
                """
          INSERT INTO level_user
          VALUES ($1,$2,$3,$4,$5)
          """,
                ctx.guild.id,
                member.id,
                0,
                level,
                int((100 * level + 1) ** 0.9),
            )

        await ctx.send_success(
            f"Set the level for {member.mention} to **Level {level}**"
        )

    @level_cmd.command(name="reset", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @leveling_enabled()
    async def level_reset(self, ctx: PretendContext, *, member: Member = None):
        """
        reset the level for a member or every member
        """

        async def no_callback(interaction: Interaction):
            embed = Embed(color=self.bot.color, description=f"Aborted the action...")
            await interaction.response.edit_message(embed=embed, view=None)

        if member is None:

            async def yes_callback(interaction: Interaction):
                await interaction.client.db.execute(
                    "DELETE FROM level_user WHERE guild_id = $1", interaction.guild.id
                )
                return await interaction.response.edit_message(
                    embed=Embed(
                        color=interaction.client.yes_color,
                        description=f"{interaction.client.yes} {interaction.user.mention}: Reset level statistics for **all** members",
                    ),
                    view=None,
                )

            mes = "Are you sure you want to **reset** level statistics for everyone in this server?"
        else:
            member = await LevelMember().convert(ctx, str(member.id))

            async def yes_callback(interaction: Interaction):
                await interaction.client.db.execute(
                    "DELETE FROM level_user WHERE guild_id = $1 AND user_id = $2",
                    interaction.guild.id,
                    member.id,
                )
                return await interaction.response.edit_message(
                    embed=Embed(
                        color=interaction.client.yes_color,
                        description=f"{interaction.client.yes} {interaction.user.mention}: Reset level statistics for {member.mention}",
                    ),
                    view=None,
                )

            mes = f"Are you sure you want to **reset** level statistics for {member.mention} in this server?"

        await ctx.confirmation_send(mes, yes_callback, no_callback)

    @level_cmd.command(name="leaderboard", aliases=["lb"])
    @leveling_enabled()
    async def level_leaderboard(self, ctx: PretendContext):
        """
        returns a top leaderboard for leveling
        """

        results = await self.bot.db.fetch(
            "SELECT * FROM level_user WHERE guild_id = $1", ctx.guild.id
        )

        def sorting(c):
            return c["level"], c["xp"]

        members = sorted(results, key=sorting, reverse=True)
        await ctx.paginate(
            [
                f"**{ctx.guild.get_member(m['user_id']) or m['user_id']}** has level **{m['level']}** ({m['xp']:,} xp)"
                for m in members
            ],
            "Level leaderboard",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @level_cmd.group(name="rewards", brief="manage server", invoke_without_command=True)
    @leveling_enabled()
    async def level_rewards(self, ctx):
        """
        get roles for leveling up
        """

        await ctx.create_pages()

    @level_rewards.command(name="add", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def level_rewards_add(
        self, ctx: PretendContext, level: int, *, role: NewRoleConverter
    ):
        """assign a reward role to a level"""
        if level < 1:
            return await ctx.send_error("Level cannot be lower than 1")

        if check := await self.bot.db.fetchrow(
            "SELECT * FROM level_rewards WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        ):
            return await ctx.send_warning(
                f"This role is **already** a reward for **Level {check['level']}**"
            )

        await self.bot.db.execute(
            "INSERT INTO level_rewards VALUES ($1,$2,$3)", ctx.guild.id, level, role.id
        )
        return await ctx.send_success(
            f"Added {role.mention} as a reward for reaching **Level {level}**"
        )

    @level_rewards.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def level_rewards_remove(
        self, ctx: PretendContext, *, role: NewRoleConverter
    ):
        """remove a reward from a level"""

        if check := await self.bot.db.fetchrow(
            "SELECT * FROM level_rewards WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
        ):
            await self.bot.db.execute(
                "DELETE FROM level_rewards WHERE guild_id = $1 AND role_id = $2",
                ctx.guild.id,
                role.id,
            )
            return await ctx.send_success(
                f"Removed a reward for reaching **Level {check['level']}**"
            )

        return await ctx.send_warning("This role is **not** a reward for any level")

    @level_rewards.command(name="reset", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def level_rewards_reset(self, ctx: PretendContext):
        """delete every reward that was added"""

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                "DELETE FROM level_rewards WHERE guild_id = $1", interaction.guild.id
            )
            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Removed every reward that was saved in this server",
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction):
            await interaction.response.edit_message(
                embed=Embed(color=self.bot.color, description=f"Aborted the action..."),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure that you want to **remove** every reward saved in this server?",
            yes_callback,
            no_callback,
        )

    @level_rewards.command(name="list")
    async def level_rewards_list(self, ctx: PretendContext):
        """get a list of every role reward in this server"""
        check = await self.bot.db.fetch(
            "SELECT role_id, level FROM level_rewards WHERE guild_id = $1", ctx.guild.id
        )
        roles = sorted(check, key=lambda c: c["level"])
        await ctx.paginate(
            [
                f"{ctx.guild.get_role(r['role_id']).mention} for **Level {r['level']}**"
                for r in roles
            ],
            f"Level rewards ({len(roles)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Leveling(bot))
