import uwuify
import discord
import datetime
import aiohttp
import secrets
import asyncio
from cogs.auth import TrialView
from tools.bot import Pretend
from tools.helpers import PretendContext

bot = Pretend()


@bot.check
async def check_availability(ctx: PretendContext) -> bool:
    if ctx.guild.me.joined_at.timestamp() < 1713438055:
        return True

    premium = await ctx.bot.db.fetchrow(
        "SELECT * FROM authorize WHERE guild_id = $1", ctx.guild.id
    )
    trial = await ctx.bot.db.fetchrow(
        "SELECT * FROM trial WHERE guild_id = $1", ctx.guild.id
    )
    if not premium and trial:
        if trial["end_date"] < int(datetime.datetime.now().timestamp()):
            await ctx.send_error(
                f"The trial period of using **{ctx.bot.user.name}** has ended. To continue using this bot please purchase a subscription in our [**support server**](https://discord.gg/pretendbot)"
            )
            return False
    elif not premium and not trial:
        embed = discord.Embed(
            color=ctx.bot.color,
            description=f"Are you sure you want to activate the **7 day** trial for **{ctx.bot.user.name}**?",
        )
        await ctx.reply(embed=embed, view=TrialView())
        return False

    return True


@bot.check
async def disabled_command(ctx: PretendContext):
    if await ctx.bot.db.fetchrow(
        """
    SELECT * FROM disablecmd
    WHERE guild_id = $1
    AND cmd = $2
    """,
        ctx.guild.id,
        str(ctx.command),
    ):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send_error(
                f"The command **{str(ctx.command)}** is **disabled** in this server"
            )
            return False
        return True

    global_disabled = await ctx.bot.db.fetchrow(
        """
   SELECT disabled FROM global_disabled_cmds
   WHERE cmd = $1
   """,
        ctx.bot.get_command(str(ctx.command)).name,
    )
    if global_disabled:
        if global_disabled.get("disabled") and ctx.author.id not in ctx.bot.owner_ids:
            await ctx.send_warning(
                "This command is currently disabled by the admin team of pretend, for further information please join the [Pretend Server](https://discord.gg/pretendbot)."
            )
            return False
    return True


@bot.check
async def disabled_module(ctx: PretendContext):
    if ctx.command.cog:
        if await ctx.bot.db.fetchrow(
            """
      SELECT FROM disablemodule
      WHERE guild_id = $1
      AND module = $2
      """,
            ctx.guild.id,
            ctx.command.cog_name,
        ):
            if not ctx.author.guild_permissions.administrator:
                await ctx.send_warning(
                    f"The module **{str(ctx.command.cog_name.lower())}** is **disabled** in this server"
                )
                return False
            else:
                return True
        else:
            return True
    else:
        return True


@bot.check
async def restricted_command(ctx: PretendContext):
    if ctx.guild is None or ctx.guild.owner is None:
        return True
    if ctx.author.id == ctx.guild.owner.id:
        return True

    if check := await ctx.bot.db.fetch(
        """
    SELECT * FROM restrictcommand
    WHERE guild_id = $1
    AND command = $2
    """,
        ctx.guild.id,
        ctx.command.qualified_name,
    ):
        for row in check:
            role = ctx.guild.get_role(row["role_id"])
            if not role:
                await ctx.bot.db.execute(
                    """
          DELETE FROM restrictcommand
          WHERE role_id = $1
          """,
                    row["role_id"],
                )

            if not role in ctx.author.roles:
                await ctx.send_warning(f"You cannot use `{ctx.command.qualified_name}`")
                return False
            return True
    return True


@bot.tree.context_menu(name="avatar")
async def avatar_user(interaction: discord.Interaction, member: discord.Member):
    """
    Get a member's avatar
    """

    embed = discord.Embed(
        color=await interaction.client.dominant_color(member.display_avatar.url),
        title=f"{member.name}'s avatar",
        url=member.display_avatar.url,
    )

    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.context_menu(name="banner")
async def banner_user(interaction: discord.Interaction, member: discord.Member):
    """
    Get a member's banner
    """

    member = await interaction.client.fetch_user(member.id)

    if not member.banner:
        return await interaction.warn(f"{member.mention} doesn't have a banner")

    banner = member.banner.url
    embed = discord.Embed(
        color=await interaction.client.dominant_color(banner),
        title=f"{member.name}'s banner",
        url=banner,
    )
    embed.set_image(url=member.banner.url)
    return await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    bot.run()
