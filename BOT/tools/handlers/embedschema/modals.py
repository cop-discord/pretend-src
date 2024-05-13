import datetime

from discord import TextStyle, Interaction, Member
from discord.ui import Modal, TextInput


class FooterModal(Modal, title="Edit your embed"):
    text = TextInput(label="footer text", required=False)
    icon = TextInput(label="footer icon", required=False)

    def variable_replace(self, member: Member, params: str) -> str:
        if "{user.avatar}" in params:
            params = params.replace("{user.avatar}", member.display_avatar.url)
        if "{guild.icon}" in params:
            params = params.replace("{guild.icon}", str(member.guild.icon))

        return params

    async def on_submit(self, interaction: Interaction) -> None:
        embed = interaction.message.embeds[0]
        if self.text.value == "":
            if embed.footer:
                text = embed.footer.text
            else:
                text = None
        else:
            text = self.text.value

        if self.icon.value == "":
            if embed.footer:
                icon = embed.footer.icon_url
            else:
                icon = None
        else:
            icon = self.variable_replace(interaction.user, self.icon.value)

        embed.set_footer(text=text, icon_url=icon)
        await interaction.response.edit_message(embed=embed)

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await interaction.warn(
            f"A problem occured while trying to edit your embed - {error}",
            ephemeral=True,
        )


class ImagesModal(Modal, title="Edit your embed"):
    thumbnail = TextInput(label="thumbnail image", required=False)
    image = TextInput(label="image", required=False)

    def variable_replace(self, member: Member, params: str) -> str:
        if "{user.avatar}" in params:
            params = params.replace("{user.avatar}", member.display_avatar.url)
        if "{guild.icon}" in params:
            params = params.replace("{guild.icon}", str(member.guild.icon))

        return params

    async def on_submit(self, interaction: Interaction) -> None:
        embed = interaction.message.embeds[0]
        thumbnail = None
        image = None

        if self.thumbnail.value == "":
            if embed.thumbnail:
                thumbnail = embed.thumbnail.url
            else:
                thumbnail = None
        else:
            thumbnail = self.variable_replace(interaction.user, self.thumbnail.value)

        if self.image.value == "":
            if embed.image:
                image = embed.image.url
            else:
                image = None
        else:
            image = self.variable_replace(interaction.user, self.image.value)

        embed.set_image(url=image)
        embed.set_thumbnail(url=thumbnail)
        await interaction.response.edit_message(embed=embed)

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await interaction.warn(
            f"A problem occured while trying to edit your embed - {error}",
            ephemeral=True,
        )


class AuthorModal(Modal, title="Edit your embed"):
    name = TextInput(label="author name", required=False)
    icon = TextInput(label="author icon", required=False)

    def variable_replace(self, member: Member, params: str) -> str:
        if "{user.avatar}" in params:
            params = params.replace("{user.avatar}", member.display_avatar.url)
        if "{guild.icon}" in params:
            params = params.replace("{guild.icon}", str(member.guild.icon))

        return params

    async def on_submit(self, interaction: Interaction) -> None:
        embed = interaction.message.embeds[0]
        if embed.author:
            name = embed.author.name
            icon = embed.author.icon_url
        else:
            name = None
            icon = None

        if self.name.value != "":
            name = self.name.value

        if self.icon.value != "":
            icon = self.icon.value

        embed.set_author(
            name=name, icon_url=self.variable_replace(interaction.user, icon)
        )
        await interaction.response.edit_message(embed=embed)

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await interaction.warn(
            f"A problem occured while trying to edit your embed - {error}",
            ephemeral=True,
        )


class BasicModal(Modal, title="Edit your embed"):
    content = TextInput(label="content", required=False)
    tit = TextInput(label="title", required=False)
    desc = TextInput(
        label="description", style=TextStyle.long, max_length=2000, required=False
    )
    color = TextInput(label="hex color", required=False, max_length=7)
    timestamp = TextInput(
        label="timestamp", placeholder="either yes or no. nothing else", required=False
    )

    async def on_submit(self, interaction: Interaction) -> None:
        embed = interaction.message.embeds[0]
        if self.tit.value != "":
            embed.title = self.tit.value

        if self.desc.value != "":
            embed.description = self.desc.value

        if self.color.value != "":
            try:
                color = int(self.color.value.replace("#", ""), 16)
                embed.color = color
            except:
                embed.color = interaction.client.color

        if self.timestamp.value.lower() == "yes":
            embed.timestamp = datetime.datetime.now()

        if self.content.value != "":
            content = self.content.value
        else:
            content = interaction.message.content

        await interaction.response.edit_message(content=content, embed=embed)

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await interaction.warn(
            f"A problem occured while trying to edit your embed - {error}",
            ephemeral=True,
        )
