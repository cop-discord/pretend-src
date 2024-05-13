import os
import asyncio

import discord
from discord.ext import commands

from typing import Literal
from tools.bot import Pretend
from tools.helpers import PretendContext


class Autopfp(commands.Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot

    @commands.hybrid_group(invoke_without_command=True)
    async def autopfp(self, ctx: PretendContext):
        """
        Automatically send pfps to a channel in this server
        """

        return await ctx.create_pages()

    @autopfp.command(name="add", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_webhooks=True)
    async def autopfp_add(
        self,
        ctx: PretendContext,
        channel: discord.TextChannel,
        category: Literal[
            "random", "roadmen", "girl", "egirl", "anime", "ceinory"
        ] = "random",
    ):
        """
        Add an autopfp channel
        """

        await self.bot.db.execute(
            """
            INSERT INTO autopfp VALUES ($1,$2,$3,$4)
            ON CONFLICT (guild_id, type, category) DO UPDATE
            SET channel_id = $4
            """,
            ctx.guild.id,
            "pfps",
            category,
            channel.id,
        )

        if not self.bot.pfps_send:
            self.bot.pfps_send = True
            asyncio.ensure_future(self.bot.autoposting("pfps"))

        return await ctx.send_success(
            f"Sending **{category}** pfps to {channel.mention}"
        )

    @autopfp.command(name="remove", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def autopfp_remove(
        self,
        ctx: PretendContext,
        category: Literal[
            "random", "roadmen", "girl", "egirl", "anime", "ceinory"
        ] = "random",
    ):
        """
        Remove an autopfp channel
        """

        await self.bot.db.execute(
            """
            DELETE FROM autopfp WHERE guild_id = $1 
            AND type = $2 AND category = $3
            """,
            ctx.guild.id,
            "pfps",
            category,
        )

        return await ctx.send_success(f"Stopped sending **{category}** pfps")

    @commands.hybrid_group()
    async def autobanner(self, ctx: PretendContext):
        """
        Automatically send banners to a channel
        """

        return await ctx.create_pages()

    @autobanner.command(name="add", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_webhooks=True)
    async def autobanner_add(
        self,
        ctx: PretendContext,
        channel: discord.TextChannel,
        category: Literal["random", "cute", "mix", "imsg"] = "random",
    ):
        """
        Add an autobanner channel
        """

        await self.bot.db.execute(
            """
            INSERT INTO autopfp VALUES ($1,$2,$3,$4)
            ON CONFLICT (guild_id, type, category) DO UPDATE
            SET channel_id = $4
            """,
            ctx.guild.id,
            "banners",
            category,
            channel.id,
        )

        if not self.bot.banners_send:
            self.bot.banners_send = True
            asyncio.ensure_future(self.bot.autoposting("banners"))

        return await ctx.send_success(
            f"Sending **{category}** banners to {channel.mention}"
        )

    @autobanner.command(name="remove", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def autobanner_remove(
        self,
        ctx: PretendContext,
        category: Literal["random", "cute", "mix", "imsg"] = "random",
    ):
        """
        Remove an autobanner channel
        """

        await self.bot.db.execute(
            """
            DELETE FROM autopfp WHERE guild_id = $1 
            AND type = $2 AND category = $3
            """,
            ctx.guild.id,
            "banners",
            category,
        )

        return await ctx.send_success(f"Stopped sending **{category}** banners")

    @commands.hybrid_command(name="report")
    async def report(
        self,
        ctx: PretendContext,
        type: Literal["banners", "pfps"],
        category: Literal[
            "cute", "mix", "anime", "girl", "egirl", "roadmen", "ceinory"
        ],
        image_id: str,
    ):
        """
        Report a picture sent by pretend via autopfp
        """

        directory = f"./PretendImages/{type.capitalize()}/"

        if not category.capitalize() in os.listdir(directory):
            return await ctx.send_warning(f"This is not a **{type}** category")

        directory += f"{category.capitalize()}/"

        if not image_id in [i[:-4] for i in os.listdir(directory)]:
            return await ctx.send_warning("This is not a valid image id")

        file_path = os.path.join(
            directory, next(e for e in os.listdir(directory) if image_id == e[:-4])
        )
        file = discord.File(file_path)
        embed = discord.Embed(color=self.bot.color)

        embed.set_image(url=f"attachment://{file.filename}")
        embed.set_footer(text=f"{type} module: {category} • id: {image_id} • /report")

        channel = self.bot.get_channel(1224395162172784670)
        try:
            await channel.send(
                f"**{ctx.author}** reported a picture in **{ctx.guild}** (`{ctx.guild.id}`)",
                embed=embed,
                file=file,
            )
        except discord.Forbidden:
            print(
                "Avatar reports channel not found/can't be accessed."
                + f"\n{ctx.author} ({ctx.author.id}) reported the image with ID {image_id} in the {category} category."
            )

        return await ctx.send_success(f"Reported picture with ID **{image_id}**")


async def setup(bot):
    await bot.add_cog(Autopfp(bot))
