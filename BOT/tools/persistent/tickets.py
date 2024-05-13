import os
import asyncio
import discord
import datetime
from discord.ext import commands
import chat_exporter
import secrets
from discord import (
    PermissionOverwrite,
    Member,
    Embed,
    File,
    Role,
    CategoryChannel,
    TextChannel,
    Interaction,
    ButtonStyle,
    SelectOption,
)


class TicketTopic(discord.ui.Modal, title="Add a ticket topic"):

    name = discord.ui.TextInput(
        label="topic name",
        placeholder="the ticket topic's name..",
        required=True,
        style=discord.TextStyle.short,
    )

    description = discord.ui.TextInput(
        label="topic description",
        placeholder="the description of the ticket topic...",
        required=False,
        max_length=100,
        style=discord.TextStyle.long,
    )

    async def on_submit(self, interaction: discord.Interaction):
        check = await interaction.client.db.fetchrow(
            "SELECT * FROM ticket_topics WHERE guild_id = $1 AND name = $2",
            interaction.guild.id,
            self.name.value,
        )

        if check:
            return await interaction.response.send_message(
                f"A topic with the name **{self.name.value}** already exists",
                ephemeral=True,
            )

        await interaction.client.db.execute(
            "INSERT INTO ticket_topics VALUES ($1,$2,$3)",
            interaction.guild.id,
            self.name.value,
            self.description.value,
        )
        return await interaction.response.send_message(
            f"Added new ticket topic **{self.name.value}**", ephemeral=True
        )


class OpenTicket(discord.ui.Button):
    def __init__(self, bot: commands.AutoShardedBot):
        super().__init__(label="Create", emoji="🎫", custom_id="ticket_open:persistent")
        self.bot = bot

    async def create_channel(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        title: str = None,
        topic: str = None,
        embed: str = None,
    ):
        view = TicketView(self.bot)
        view.delete_ticket()
        if category:
            overwrites = category.overwrites
        else:
            overwrites = {}
        che = await interaction.client.db.fetchrow(
            "SELECT support_id FROM tickets WHERE guild_id = $1", interaction.guild.id
        )
        if che:
            role = interaction.guild.get_role(che[0])
            if role:
                overwrites.update(
                    {
                        role: discord.PermissionOverwrite(
                            manage_permissions=True,
                            read_messages=True,
                            send_messages=True,
                            attach_files=True,
                            embed_links=True,
                            manage_messages=True,
                        )
                    }
                )
        overwrites.update(
            {
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                )
            }
        )
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            topic=f"A ticket opened by {interaction.user.name} ({interaction.user.id})",
            reason=f"Ticket opened by {interaction.user.name}",
            overwrites=overwrites,
        )
        await self.bot.db.execute(
            "INSERT INTO opened_tickets VALUES ($1,$2,$3)",
            interaction.guild.id,
            channel.id,
            interaction.user.id,
        )
        if not embed:
            embed = (
                """{embed}{color: #181a14}$v{title: {title}}$v{description: Support will be with you shortly
To close the ticket please press 🗑️}$v{author: name: {bot.name} && icon: {bot.avatar}}$v{content: {user.mention}}""".replace(
                    "{title}", title or "Ticket opened"
                )
                .replace("{bot.name}", interaction.client.user.name)
                .replace("{bot.avatar}", interaction.client.user.display_avatar.url)
            )
        x = await self.bot.embed_build.alt_convert(
            interaction.user, embed.replace("{topic}", topic or "none")
        )
        x["view"] = view
        mes = await channel.send(**x, allowed_mentions=discord.AllowedMentions.all())
        await mes.pin(reason="pinned the ticket message")
        return channel

    async def callback(self, interaction: discord.Interaction) -> None:
        check = await interaction.client.db.fetchrow(
            "SELECT * FROM tickets WHERE guild_id = $1", interaction.guild.id
        )
        if not check:
            return await interaction.response.send_message(
                "Tickets module is disabled in this server", ephemeral=True
            )
        if await interaction.client.db.fetchrow(
            "SELECT * FROM opened_tickets WHERE guild_id = $1 AND user_id = $2",
            interaction.guild.id,
            interaction.user.id,
        ):
            return await interaction.response.send_message(
                "You **already** have an opened ticket", ephemeral=True
            )
        results = await interaction.client.db.fetch(
            "SELECT * FROM ticket_topics WHERE guild_id = $1", interaction.guild.id
        )
        category = interaction.guild.get_channel(check["category_id"])
        open_embed = check["open_embed"]
        if len(results) == 0:
            channel = await self.create_channel(
                interaction, category, title=None, topic=None, embed=open_embed
            )
            return await interaction.response.send_message(
                embed=discord.Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Opened ticket for you in {channel.mention}",
                ),
                ephemeral=True,
            )
        else:
            options = [
                discord.SelectOption(
                    label=result["name"], description=result["description"]
                )
                for result in results
            ]
            embed = discord.Embed(
                color=interaction.client.color, description="🔍 Select a topic"
            )
            select = discord.ui.Select(options=options, placeholder="Topic menu")

            async def select_callback(inter: discord.Interaction) -> None:
                channel = await self.create_channel(
                    interaction,
                    category,
                    title=f"topic: {select.values[0]}",
                    topic=select.values[0],
                    embed=open_embed,
                )
                return await inter.response.edit_message(
                    view=None,
                    embed=discord.Embed(
                        color=inter.client.yes_color,
                        description=f"{inter.client.yes} {inter.user.mention}: Opened ticket for you in {channel.mention}",
                    ),
                )

            select.callback = select_callback
            view = discord.ui.View(timeout=None)
            view.add_item(select)
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )


class DeleteTicket(discord.ui.Button):
    def __init__(self):
        super().__init__(emoji="🗑️", custom_id="ticket_close:persistent")

    async def make_transcript(self, c: TextChannel):
        logId = secrets.token_hex(16)
        logs_directory = "/home/damon/PretendLogs/logs"
        file = f"{logs_directory}/{str(logId)}.html"
        os.makedirs(logs_directory, exist_ok=True)
        messages = await chat_exporter.export(c)
        with open(file, "w", encoding="utf-8") as f:
            f.write(messages)
        return f"https://logs.pretend.best/{logId}"

    async def callback(self, interaction: discord.Interaction) -> None:

        che = await interaction.client.db.fetchrow(
            "SELECT support_id FROM tickets WHERE guild_id = $1", interaction.guild.id
        )
        if che:
            role = interaction.guild.get_role(che[0])
            if role:
                if (
                    not role in interaction.user.roles
                    and not interaction.user.guild_permissions.manage_channels
                ):
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            color=interaction.client.warning_color,
                            description=f"{interaction.client.warning} {interaction.user.mention}: Only members with {role.mention} role or members with `manage_channels` permission can close tickets",
                        ),
                        ephemeral=True,
                        view=None,
                    )
            else:
                if not interaction.user.guild_permissions.manage_channels:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            color=interaction.client.warning_color,
                            description=f"{interaction.client.warning} {interaction.user.mention}: Only members with `manage_channels` permission can close tickets",
                        ),
                        ephemeral=True,
                        view=None,
                    )
        else:
            if not interaction.user.guild_permissions.manage_channels:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        color=interaction.client.warning_color,
                        description=f"{interaction.client.warning} {interaction.user.mention}: Only members with `manage_channels` permission can close tickets",
                    ),
                    ephemeral=True,
                    view=None,
                )

        view = discord.ui.View(timeout=None)
        yes = discord.ui.Button(label="yes", style=discord.ButtonStyle.success)
        no = discord.ui.Button(label="no", style=discord.ButtonStyle.danger)

        async def yes_callback(inter: discord.Interaction) -> None:
            check = await inter.client.db.fetchrow(
                "SELECT logs FROM tickets WHERE guild_id = $1", inter.guild.id
            )
            if check:
                channel = inter.guild.get_channel(check[0])
                if channel:
                    url = await self.make_transcript(inter.channel)
                    e = discord.Embed(
                        color=inter.client.color,
                        title=f"Logs for {inter.channel.name} `{inter.channel.id}`",
                        description=f"Closed by **{inter.user}**",
                        timestamp=datetime.datetime.now(),
                        url=url,
                    )
            await inter.response.edit_message(
                content="Deleting this channel in 5 seconds", view=None
            )
            await asyncio.sleep(5)
            await inter.channel.delete(reason="ticket closed")

        async def no_callback(inter: discord.Interaction) -> None:
            await inter.response.edit_message(
                content="You changed your mind", view=None
            )

        yes.callback = yes_callback
        no.callback = no_callback
        view.add_item(yes)
        view.add_item(no)
        return await interaction.response.send_message(
            "Are you sure you want to close this ticket?", view=view
        )


class TicketView(discord.ui.View):
    def __init__(self, bot: commands.AutoShardedBot, adding: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.adding = adding
        if self.adding is True:
            self.add_item(OpenTicket(self.bot))
            self.add_item(DeleteTicket())

    def create_ticket(self):
        self.add_item(OpenTicket(self.bot))

    def delete_ticket(self):
        self.add_item(DeleteTicket())
