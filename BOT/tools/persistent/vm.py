import datetime

from discord.interactions import Interaction

from tools.exceptions import RenameRateLimit

from discord import (
    Embed,
    Interaction,
    TextStyle,
    SelectOption,
    ButtonStyle,
    Guild,
    utils,
    VoiceChannel,
)
from discord.ui import Modal, Button, View, TextInput, Select
from discord.ext.commands import AutoShardedBot, CommandError


async def rename_vc_bucket(bot: AutoShardedBot, channel: VoiceChannel):
    """Prevents the bot from rate limiting while renaming channels"""
    bucket = bot.cache.get(f"vc-bucket-{channel.id}")
    if not bucket:
        bucket = []
    bucket.append(datetime.datetime.now())
    to_remove = [
        d for d in bucket if (datetime.datetime.now() - d).total_seconds() > 600
    ]
    for l in to_remove:
        bucket.remove(l)
    await bot.cache.set(f"vc-bucket-{channel.id}", bucket)
    if len(bucket) >= 3:
        raise RenameRateLimit()
    return True


class ButtonScript:

    def script(params: str):
        x = {}
        fields = []
        content = None
        list = []
        params = params.replace("{embed}", "")
        parts = [p[1:][:-1] for p in params.split("$v")]

        for part in parts:
            if part.startswith("content:"):
                content = part[len("content:") :]

            if part.startswith("title:"):
                x["title"] = part[len("title:") :]

            if part.startswith("description:"):
                x["description"] = part[len("description:") :]

            if part.startswith("color:"):
                try:
                    x["color"] = int(part[len("color:") :].replace("#", ""), 16)
                except:
                    x["color"] = 2699885

            if part.startswith("thumbnail:"):
                x["thumbnail"] = {"url": part[len("thumbnail:") :]}

            if part.startswith("image:"):
                x["image"] = {"url": part[len("image:") :]}

            if part == "timestamp":
                x["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

            if part.startswith("author:"):
                author_parts = part[len("author: ") :].split(" && ")
                name = None
                url = None
                icon_url = None

                for z in author_parts:

                    if z.startswith("name:"):
                        name = z[len("name:") :]

                    if z.startswith("icon:"):
                        icon_url = z[len("icon:") :]

                    if z.startswith("url:"):
                        url = z[len("url:") :]

                    x["author"] = {"name": name}

                    if icon_url:
                        x["author"]["icon_url"] = icon_url
                    if url:
                        x["author"]["url"] = url
            if part.startswith("field:"):
                name = None
                value = None
                inline = True
                field_parts = part[len("field: ") :].split(" && ")

                for z in field_parts:

                    if z.startswith("name:"):
                        name = z[len("name:") :]

                    if z.startswith("value:"):
                        value = z[len("value:") :]

                    if z.startswith("inline:"):
                        inline = bool(z[len("inline:") :].lower() == "true")

                    fields.append({"name": name, "value": value, "inline": inline})

            if part.startswith("footer:"):
                text = None
                icon_url = None
                footer_parts = part[len("footer: ") :].split(" && ")

                for z in footer_parts:

                    if z.startswith("text:"):
                        text = z[len("text:") :]

                    if z.startswith("icon:"):
                        icon_url = z[len("icon:") :]

                x["footer"] = {"text": text, "icon_url": icon_url}

            if part.startswith("button:"):
                choices = part[len("button: ") :].split(" && ")
                button_action = choices[0]
                label = ""
                emoji = None
                style = "gray"

                for choice in choices:

                    if choice.startswith("label:"):
                        label = choice[len("label: ") :]

                    if choice.startswith("emoji:"):
                        emoji = choice[len("emoji: ") :]

                    if choice.startswith("style:"):
                        style = choice[len("style: ") :]

                list.append((button_action, label, emoji, style))
        if not x:
            embed = None
        else:
            x["fields"] = fields
            embed = Embed.from_dict(x)
        return content, embed, list


class InteractionMes:
    async def vc_task(interaction: Interaction) -> bool:
        if not interaction.user.voice:
            await interaction.warn("You are **not** in a voice channel", ephemeral=True)
            return False

        re = await interaction.client.db.fetchrow(
            "SELECT channel_id FROM voicemaster WHERE guild_id = $1",
            interaction.guild.id,
        )
        if not re:
            await interaction.warn("VoiceMaster is **not** configured", ephemeral=True)
            return False
        channel = interaction.guild.get_channel(re[0])
        if not channel:
            await interaction.warn(
                "VoiceMaster main channel **not** found", ephemeral=True
            )
            return False
        if interaction.user.voice.channel.category_id != channel.category_id:
            await interaction.warn(
                "You are not in a voice channel created by the bot", ephemeral=True
            )
            return False
        check = await interaction.client.db.fetchrow(
            "SELECT user_id FROM vcs WHERE voice = $1",
            interaction.user.voice.channel.id,
        )
        if check[0] != interaction.user.id:
            await interaction.warn(
                "You are **not** the **owner** of this voice channel", ephemeral=True
            )
            return False
        return True


class RenameModal(Modal, title="rename your voice channel"):
    name = TextInput(
        label="voice channel name",
        placeholder="the new voice channel name...",
        style=TextStyle.short,
    )

    async def on_submit(self, interaction: Interaction) -> None:
        await rename_vc_bucket(interaction.client, interaction.user.voice.channel)
        await interaction.user.voice.channel.edit(
            name=self.name.value,
            reason=f"Voice channel name changed by {interaction.user}",
        )
        await interaction.approve(
            f"Voice channel name changed to **{self.name.value}**", ephemeral=True
        )

    async def on_error(self, interaction: Interaction, error: CommandError):
        if isinstance(error, RenameRateLimit):
            return await interaction.warn(error.message, ephemeral=True)
        return await interaction.warn(error.args[0], ephemeral=True)


class rename(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, style=style, emoji=emoji, custom_id="persistent_view:rename"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            await interaction.response.send_modal(RenameModal())


class lock(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, style=style, emoji=emoji, custom_id="persistent_view:lock"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            overwrite = interaction.user.voice.channel.overwrites_for(
                interaction.guild.default_role
            )
            overwrite.connect = False
            await interaction.user.voice.channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel locked by {interaction.user}",
            )
            return await interaction.approve(
                f"Locked {interaction.user.voice.channel.mention}", ephemeral=True
            )


class unlock(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, style=style, emoji=emoji, custom_id="persistent_view:unlock"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            overwrite = interaction.user.voice.channel.overwrites_for(
                interaction.guild.default_role
            )
            overwrite.connect = True
            await interaction.user.voice.channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel unlocked by {interaction.user}",
            )
            return await interaction.approve(
                f"Unlocked {interaction.user.voice.channel.mention}", ephemeral=True
            )


class hide(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:hide"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            overwrite = interaction.user.voice.channel.overwrites_for(
                interaction.guild.default_role
            )
            overwrite.view_channel = False
            await interaction.user.voice.channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel hidden by {interaction.user}",
            )
            return await interaction.approve(
                f"Hidden {interaction.user.voice.channel.mention}", ephemeral=True
            )


class reveal(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:reveal"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            overwrite = interaction.user.voice.channel.overwrites_for(
                interaction.guild.default_role
            )
            overwrite.view_channel = True
            await interaction.user.voice.channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel revealed by {interaction.user}",
            )
            return await interaction.approve(
                f"Revealed {interaction.user.voice.channel.mention}", ephemeral=True
            )


class decrease(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:decrease"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            if interaction.user.voice.channel.user_limit == 0:
                return await interaction.warn(
                    "Limit cannot be lower than 0", ephemeral=True
                )
            await interaction.user.voice.channel.edit(
                user_limit=interaction.user.voice.channel.user_limit - 1,
                reason=f"Channel user limit decreased by {interaction.user}",
            )
            return await interaction.approve(
                f"Decreased {interaction.user.voice.channel.mention}'s member limit",
                ephemeral=True,
            )


class increase(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:increase"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            if interaction.user.voice.channel.user_limit == 99:
                return await interaction.warn(
                    "Limit cannot be higher than 99", ephemeral=True
                )
            await interaction.user.voice.channel.edit(
                user_limit=interaction.user.voice.channel.user_limit + 1,
                reason=f"Channel user limit increased by {interaction.user}",
            )
            return await interaction.approve(
                f"Increased {interaction.user.voice.channel.mention}'s member limit",
                ephemeral=True,
            )


class info(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:info"
        )

    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user.voice:
            return await interaction.warn(
                "You are **not** in a voice channel", ephemeral=True
            )
        check = await interaction.client.db.fetchrow(
            "SELECT user_id FROM vcs WHERE voice = $1",
            interaction.user.voice.channel.id,
        )
        member = interaction.guild.get_member(check[0])
        embed = Embed(
            color=interaction.client.color,
            title=interaction.user.voice.channel.name,
            description=f"owner: **{member}** (`{member.id}`)\ncreated: **{utils.format_dt(interaction.user.voice.channel.created_at, style='R')}**\nbitrate: **{interaction.user.voice.channel.bitrate/1000}kbps**\nconnected: **{len(interaction.user.voice.channel.members)} member{'s' if len(interaction.user.voice.channel.members) > 1 else ''}**",
        )
        embed.set_author(
            name=interaction.user.name, icon_url=interaction.user.display_avatar
        )
        embed.set_thumbnail(url=member.display_avatar)
        await interaction.response.send_message(embed=embed, view=None, ephemeral=True)


class claim(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:claim"
        )

    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user.voice:
            return await interaction.warn(
                "You are **not** in a voice channel", ephemeral=True
            )
        check = await interaction.client.db.fetchrow(
            "SELECT user_id FROM vcs WHERE voice = $1",
            interaction.user.voice.channel.id,
        )
        if (
            interaction.guild.get_member(check[0])
            in interaction.user.voice.channel.members
        ):
            return await interaction.warn(
                "The owner is still in the voice channel", ephemeral=True
            )
        await interaction.client.db.execute(
            "UPDATE vcs SET user_id = $1 WHERE voice = $2",
            interaction.user.id,
            interaction.user.voice.channel.id,
        )
        return await interaction.approve(
            "You are the new owner of the voice channel", ephemeral=True
        )


class kick(Button):
    def __init__(self, label, emoji, style):
        super().__init__(
            label=label, emoji=emoji, style=style, custom_id="persistent_view:kick"
        )

    async def callback(self, interaction: Interaction) -> None:
        if await InteractionMes.vc_task(interaction):
            if len(interaction.user.voice.channel.members) < 2:
                return await interaction.warn(
                    "You are the only member in the voice channel", ephemeral=True
                )
            options = [
                SelectOption(label=str(m), value=str(m.id))
                for m in interaction.user.voice.channel.members
                if m.id != interaction.user.id
            ]
            select = Select(
                options=options, placeholder="Who do i kick?", max_values=len(options)
            )

            async def select_callback(inter: Interaction) -> None:
                for values in select.values:
                    member = inter.guild.get_member(int(values))
                    await member.move_to(
                        channel=None,
                        reason=f"Member kicked from voice channel by {inter.user}",
                    )
                await inter.response.edit_message(
                    content=f"kicked {len(select.values)} members from your voice channel",
                    view=None,
                )

            select.callback = select_callback
            view = View()
            view.add_item(select)
            await interaction.response.send_message(
                "Use the dropdown menu to select the members", view=view, ephemeral=True
            )


class VoiceMasterView(View):
    def __init__(self, bot: AutoShardedBot, to_add: list = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.styles = {
            "red": ButtonStyle.danger,
            "green": ButtonStyle.green,
            "blue": ButtonStyle.blurple,
            "gray": ButtonStyle.gray,
        }
        if to_add:
            for result in to_add:
                try:
                    self.readd_button(
                        result["action"],
                        label=result["label"],
                        emoji=result["emoji"],
                        style=result["style"],
                    )
                except:
                    continue

    def readd_button(
        self, action: str, /, *, label: str = "", emoji=None, style: str = "gray"
    ):
        action = action.strip().lower()
        if action == "lock":
            self.add_item(lock(label, emoji, self.styles.get(style)))
        elif action == "unlock":
            self.add_item(unlock(label, emoji, self.styles.get(style)))
        elif action == "hide":
            self.add_item(hide(label, emoji, self.styles.get(style)))
        elif action == "reveal":
            self.add_item(reveal(label, emoji, self.styles.get(style)))
        elif action == "decrease":
            self.add_item(decrease(label, emoji, self.styles.get(style)))
        elif action == "increase":
            self.add_item(increase(label, emoji, self.styles.get(style)))
        elif action == "info":
            self.add_item(info(label, emoji, self.styles.get(style)))
        elif action == "kick":
            self.add_item(kick(label, emoji, self.styles.get(style)))
        elif action == "claim":
            self.add_item(claim(label, emoji, self.styles.get(style)))
        elif action == "rename":
            self.add_item(rename(label, emoji, self.styles.get(style)))

    async def add_button(
        self,
        guild: Guild,
        action: str,
        /,
        *,
        label: str = "",
        emoji=None,
        style: str = "gray",
    ):
        self.readd_button(action, label=label, emoji=emoji, style=style)
        await self.bot.db.execute(
            "INSERT INTO vm_buttons VALUES ($1,$2,$3,$4,$5)",
            guild.id,
            action,
            label,
            emoji,
            style,
        )

    async def add_default_buttons(self, guild: Guild):
        for action in [
            ("<:lock:1188943564051325028>", "lock"),
            ("<:unlock:1188945889423785984>", "unlock"),
            ("<:ghost:1188943552995131452>", "hide"),
            ("<:unghost:1188943588986462209>", "reveal"),
            ("<:rename:1188943581843574915>", "rename"),
            ("<:minus:1188945883472076870>", "decrease"),
            ("<:plus:1188945888433930350>", "increase"),
            ("<:info:1188946782277877760>", "info"),
            ("<:kick:1188943566123319429>", "kick"),
            ("<:claim:1188943555092287549>", "claim"),
        ]:
            await self.add_button(guild, action[1], emoji=action[0])
