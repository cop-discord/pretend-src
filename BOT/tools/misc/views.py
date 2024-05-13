import re
import datetime

from io import BytesIO
from typing import Union

from discord import (
    Interaction,
    Embed,
    ButtonStyle,
    Button,
    Member,
    TextStyle,
    PartialEmoji,
    Sticker,
    HTTPException,
    File,
    Emoji,
)
from discord.ui import View, button, Modal, TextInput
from discord.ext.commands import Context


class confessModal(Modal, title="confess here"):
    name = TextInput(
        label="confession",
        placeholder="the confession is anonymous",
        style=TextStyle.long,
    )

    async def on_submit(self, interaction: Interaction) -> None:
        check = await interaction.client.db.fetchrow(
            "SELECT * FROM confess WHERE guild_id = $1", interaction.guild.id
        )
        if check:
            if re.search(
                r"[(http(s)?):\/\/(www\.)?a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)",
                self.name.value,
            ):
                return await interaction.response.send_message(
                    "You cannot use links in a confession", ephemeral=True
                )

            channel = interaction.guild.get_channel(check["channel_id"])
            count = check["confession"] + 1
            embed = Embed(
                color=interaction.client.color,
                description=f"{interaction.user.mention}: sent your confession in {channel.mention}",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            e = Embed(
                color=interaction.client.color,
                description=f"{self.name.value}",
                timestamp=datetime.datetime.now(),
            )
            e.set_author(
                name=f"anonymous confession #{count}",
                url="https://discord.gg/pretendbot",
            )

            e.set_footer(text="type /confess to send a confession")
            await channel.send(embed=e)
            await interaction.client.db.execute(
                "UPDATE confess SET confession = $1 WHERE guild_id = $2",
                count,
                interaction.guild.id,
            )
            await interaction.client.db.execute(
                "INSERT INTO confess_members VALUES ($1,$2,$3)",
                interaction.guild.id,
                interaction.user.id,
                count,
            )

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        return await interaction.warn(f"Couldn't send your confession - {error}")


class Donate(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.responses = {
            "paypal": "https://paypal.me/vyprgroup",
            "stripe (card)": "https://buy.stripe.com/8wM00E8Dl07MafSeUW",
            "cashapp": "https://buy.stripe.com/8wM00E8Dl07MafSeUW",
        }

    async def button_callback(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(
            self.responses.get(button.custom_id), ephemeral=True
        )

    @button(emoji="<:paypal:1194992256063635547>", custom_id="paypal")
    async def paypal_payment(self, interaction: Interaction, button: Button):
        await self.button_callback(interaction=interaction, button=button)

    @button(emoji="<:stripe:1194992457935487017>", custom_id="stripe (card)")
    async def bitcoin_payment(self, interaction: Interaction, button: Button):
        await self.button_callback(interaction=interaction, button=button)

    @button(emoji="<a:cashapp:1188946775332098098>", custom_id="cashapp")
    async def cashapp_payment(self, interaction: Interaction, button: Button):
        await self.button_callback(interaction=interaction, button=button)


class BoosterMod(View):
    def __init__(self, ctx: Context, member: Member, reason: str):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.member = member
        self.reason = reason

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn(
                "You are **not** the author of this embed", ephemeral=True
            )
            return False
        if not self.ctx.guild.get_member(self.member.id):
            await interaction.warn("Member **not** found", ephemeral=True)
            return False
        return True

    @button(label="Approve", style=ButtonStyle.green)
    async def yes_button(self, interaction: Interaction, button: Button):
        if self.ctx.command.name == "ban":
            await self.member.ban(reason=self.reason)
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.bot.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Banned {self.member.mention} - {self.reason}",
                ),
                view=None,
            )
        else:
            await self.member.kick(reason=self.reason)
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.bot.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Kicked {self.member.mention} - {self.reason}",
                ),
                view=None,
            )

    @button(label="Decline", style=ButtonStyle.red)
    async def no_button(self, interaction: Interaction, button: Button):
        if self.ctx.author.id != interaction.user.id:
            return await interaction.response.send_message(
                embed=Embed(
                    color=interaction.client.warning_color,
                    description=f"{interaction.client.warning_emoji} {interaction.user.mention}: You are **not** the author of this embed",
                ),
                ephemeral=True,
            )
        await interaction.response.edit_message(
            embed=Embed(
                color=interaction.client.color, description="Cancelling action..."
            ),
            view=None,
        )


class MarryView(View):
    def __init__(self, ctx: Context, member: Member):
        super().__init__()
        self.ctx = ctx
        self.member = member
        self.status = False
        self.wedding = "💒"
        self.marry_color = 0xFF819F

    async def interaction_check(self, interaction: Interaction):
        if interaction.user == self.ctx.author:
            await interaction.warn(
                "You cannot interact with your own marriage", ephemeral=True
            )
            return False
        elif interaction.user != self.member:
            await interaction.warn(
                "You are **not** the author of this embed", ephemeral=True
            )
            return False
        return True

    @button(label="Approve", style=ButtonStyle.success)
    async def yes(self, interaction: Interaction, button: Button):
        if await interaction.client.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", self.ctx.author.id
        ):
            return await interaction.client.send_message(
                f"{self.ctx.author.mention} already accepted a marriage", ephemeral=True
            )

        if await interaction.client.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", interaction.user.id
        ):
            return await interaction.client.send_message(
                "You **already accepted a marriage", ephemeral=True
            )

        await interaction.client.db.execute(
            "INSERT INTO marry VALUES ($1,$2,$3)",
            self.ctx.author.id,
            self.member.id,
            datetime.datetime.now().timestamp(),
        )
        embe = Embed(
            color=self.marry_color,
            description=f"{self.wedding} {self.ctx.author.mention} succesfully married with {self.member.mention}",
        )
        await interaction.response.edit_message(content=None, embed=embe, view=None)
        self.status = True

    @button(label="Decline", style=ButtonStyle.danger)
    async def no(self, interaction: Interaction, button: Button):
        embe = Embed(
            color=self.marry_color,
            description=f"{self.ctx.author.mention} i'm sorry, but {self.member.mention} is probably not the right person for you",
        )
        await interaction.response.edit_message(content=None, embed=embe, view=None)
        self.status = True

    async def on_timeout(self):
        if self.status == False:
            embed = Embed(
                color=0xFF819F,
                description=f"{self.member.mention} didn't reply in time :(",
            )
            try:
                await self.message.edit(content=None, embed=embed, view=None)
            except:
                pass


class Transfer(View):
    def __init__(self, ctx: Context, to: Member, amount: float):
        super().__init__(timeout=60)
        self.to = to
        self.amount = amount
        self.ctx = ctx
        self.confirmed = False

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn(
                "You are not the author of this embed", ephemeral=True
            )
        return interaction.user.id == self.ctx.author.id

    @button(label="Approve", style=ButtonStyle.success)
    async def yes_button(self, interaction: Interaction, button: Button):
        user_cash = (
            await interaction.client.db.fetchrow(
                "SELECT cash FROM economy WHERE user_id = $1", self.to.id
            )
        )[0]
        author_cash = (
            await interaction.client.db.fetchrow(
                "SELECT cash FROM economy WHERE user_id = $1", interaction.user.id
            )
        )[0]
        if author_cash < self.amount:
            embed = Embed(
                color=interaction.client.no_color,
                description=f"{interaction.client.no} {interaction.user.mention}: You do no have enough money to transfer",
            )
            await interaction.response.edit_message(embed=embed, view=None)
            self.confirmed = True
            return

        await interaction.client.db.execute(
            "UPDATE economy SET cash = $1 WHERE user_id = $2",
            round(user_cash + self.amount, 2),
            self.to.id,
        )
        await interaction.client.db.execute(
            "UPDATE economy SET cash = $1 WHERE user_id = $2",
            round(author_cash - self.amount, 2),
            interaction.user.id,
        )
        embed = Embed(
            color=0xD3D3D3,
            description=f"{interaction.user.mention}: Transfered **{self.amount}** to {self.to.mention}",
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.confirmed = True

    @button(label="Decline", style=ButtonStyle.red)
    async def no_button(self, interaction: Interaction, button: Button):
        embed = Embed(color=interaction.client.color, description="Aborting action")
        await interaction.response.edit_message(embed=embed, view=None)
        self.confirmed = True

    async def on_timeout(self):
        if not self.confirmed:
            embed = Embed(
                color=self.ctx.bot.color, description="Transfer is now canceled"
            )
            await self.message.edit(embed=embed, view=None)


class DownloadAsset(View):
    def __init__(
        self: "DownloadAsset", ctx: Context, asset: Union[PartialEmoji, Emoji, Sticker]
    ):
        super().__init__()
        self.ctx = ctx
        self.asset = asset
        self.pressed = False

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn(
                "You are **not** the author of this embed", ephemeral=True
            )
            return False

        if not interaction.user.guild_permissions.manage_expressions:
            await interaction.warn(
                "You do not have permissions to add emojis/stickers in this server",
                ephemeral=True,
            )
            return False

        if not interaction.user.guild.me.guild_permissions.manage_expressions:
            await interaction.warn(
                "The bot doesn't have permissions to add emojis/stickers in this server",
                ephemeral=True,
            )
            return False

        return True

    @button(label="Download", style=ButtonStyle.green)
    async def download_asset(
        self: "DownloadAsset", interaction: Interaction, button: Button
    ):
        self.pressed = True
        if isinstance(self.asset, (PartialEmoji, Emoji)):
            try:
                e = await interaction.guild.create_custom_emoji(
                    name=self.asset.name,
                    image=await self.asset.read(),
                    reason=f"Emoji added by {interaction.user}",
                )

                embed = Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Added {e} as [**{e.name}**]({e.url})",
                )

            except HTTPException:
                embed = Embed(
                    color=interaction.client.warning_color,
                    description=f"{interaction.client.warning} {interaction.user.mention}: Unable to add emoji",
                )
            finally:
                await interaction.response.edit_message(
                    embed=embed, view=None, attachments=[]
                )

        else:
            try:
                file = File(BytesIO(await self.asset.read()))
                sticker = await interaction.guild.create_sticker(
                    name=self.asset.name,
                    description=self.asset.name,
                    emoji="💀",
                    file=file,
                    reason=f"Sticker created by {interaction.user}",
                )

                embed = Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Added sticker as [**{sticker.name}**]({sticker.url})",
                )

            except HTTPException:
                embed = Embed(
                    color=interaction.client.warning_color,
                    description=f"{interaction.client.warning} {interaction.user.mention}: Unable to add sticker",
                )
            finally:
                await interaction.response.edit_message(
                    embed=embed, view=None, attachments=[]
                )

    async def on_timeout(self):
        if not self.pressed:
            await self.message.edit(view=None)


class ConfirmView(View):
    def __init__(self, author_id: int, yes_func, no_func):
        self.author_id = author_id
        self.yes_func = yes_func
        self.no_func = no_func
        super().__init__()

    async def interaction_check(self, interaction: Interaction):
        if self.author_id != interaction.user.id:
            await interaction.warn(
                "You are **not** the author of this embed", ephemeral=True
            )
        return self.author_id == interaction.user.id

    @button(label="Approve", style=ButtonStyle.green)
    async def yes_button(self, interaction: Interaction, button: Button):
        await self.yes_func(interaction)

    @button(label="Decline", style=ButtonStyle.red)
    async def no_button(self, interaction: Interaction, button: Button):
        await self.no_func(interaction)
