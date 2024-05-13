from discord.ui import View, button, Button
from discord import ButtonStyle, Interaction

from tools.helpers import PretendContext
from .modals import BasicModal, AuthorModal, ImagesModal, FooterModal


class EmbedBuilding(View):
    def __init__(self, ctx: PretendContext):
        self.ctx = ctx
        super().__init__(timeout=None)

    def replace_images(self, interaction: Interaction, params: str) -> str:
        if interaction.guild.icon.url in params:
            params = params.replace(interaction.guild.icon.url, "{guild.icon}")
        if interaction.user.display_avatar.url in params:
            params = params.replace(
                interaction.user.display_avatar.url, "{user.avatar}"
            )

        return params

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn(
                "You are **not** the author of this embed", ephemeral=True
            )
            return False
        return True

    @button(label="basic")
    async def basic_info(self, interaction: Interaction, button: Button):
        return await interaction.response.send_modal(BasicModal())

    @button(label="author")
    async def author_embed(self, interaction: Interaction, button: Button):
        return await interaction.response.send_modal(AuthorModal())

    @button(label="images")
    async def embed_images(self, interaction: Interaction, button: Button):
        return await interaction.response.send_modal(ImagesModal())

    @button(label="footer")
    async def footer_embed(self, interaction: Interaction, button: Button):
        return await interaction.response.send_modal(FooterModal())

    @button(label="save", style=ButtonStyle.green)
    async def save_embed(self, interaction: Interaction, button: Button):
        embed = interaction.message.embeds[0]
        mes = "{embed}{color: " + hex(embed.color.value).replace("0x", "#") + "}"
        if embed.description != "":
            mes += "$v{description: " + embed.description + "}"
        if embed.title:
            mes += "$v{title: " + embed.title + "}"
        if embed.timestamp:
            mes += "$v{timestamp}"
        if embed.author:
            mes += "$v{author: "
            if embed.author.name and embed.author.icon_url:
                mes += (
                    "name: "
                    + embed.author.name
                    + " && "
                    + "icon: "
                    + self.replace_images(interaction, embed.author.icon_url)
                    + "}"
                )
            elif embed.author.name and not embed.author.icon_url:
                mes += "name: " + embed.author.name + "}"
            elif embed.author.icon_url and not embed.author.name:
                mes += (
                    "icon: "
                    + self.replace_images(interaction, embed.author.icon_url)
                    + "}"
                )
        if embed.image:
            mes += (
                "$v{image: " + self.replace_images(interaction, embed.image.url) + "}"
            )
        if embed.thumbnail:
            mes += (
                "$v{thumbnail: "
                + self.replace_images(interaction, embed.thumbnail.url)
                + "}"
            )
        if embed.footer:
            mes += "$v{footer: "
            if embed.footer.text and embed.footer.icon_url:
                mes += (
                    "text: "
                    + embed.footer.text
                    + " && "
                    + "icon: "
                    + self.replace_images(interaction, embed.footer.icon_url)
                    + "}"
                )
            elif embed.footer.text and not embed.footer.icon_url:
                mes += "text: " + embed.footer.text + "}"

        if interaction.message.content:
            mes += "$v{content: " + interaction.message.content + "}"

        await interaction.response.edit_message(
            content=f"```{mes}```", embed=None, view=None
        )
