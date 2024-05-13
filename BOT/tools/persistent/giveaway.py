import json

from discord.ui import View, button, Button
from discord import Interaction, ButtonStyle


class GiveawayView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(emoji="🎉", style=ButtonStyle.blurple, custom_id="persistent:join_gw")
    async def join_gw(self, interaction: Interaction, button: Button):
        check = await interaction.client.db.fetchrow(
            "SELECT * FROM giveaway WHERE guild_id = $1 AND message_id = $2",
            interaction.guild.id,
            interaction.message.id,
        )
        lis = json.loads(check["members"])
        if interaction.user.id in lis:
            button1 = Button(label="Leave the Giveaway", style=ButtonStyle.danger)

            async def button1_callback(inter: Interaction):
                lis.remove(interaction.user.id)
                await interaction.client.db.execute(
                    "UPDATE giveaway SET members = $1 WHERE guild_id = $2 AND message_id = $3",
                    json.dumps(lis),
                    inter.guild.id,
                    interaction.message.id,
                )
                interaction.message.embeds[0].set_field_at(
                    0, name="entries", value=f"{len(lis)}"
                )
                await interaction.message.edit(embed=interaction.message.embeds[0])
                return await inter.response.edit_message(
                    content="You left the giveaway", view=None
                )

            button1.callback = button1_callback
            vi = View()
            vi.add_item(button1)
            return await interaction.response.send_message(
                content="You are already in this giveaway", view=vi, ephemeral=True
            )
        else:
            lis.append(interaction.user.id)
            await interaction.client.db.execute(
                "UPDATE giveaway SET members = $1 WHERE guild_id = $2 AND message_id = $3",
                json.dumps(lis),
                interaction.guild.id,
                interaction.message.id,
            )
            interaction.message.embeds[0].set_field_at(
                0, name="entries", value=f"{len(lis)}"
            )
            return await interaction.response.edit_message(
                embed=interaction.message.embeds[0]
            )
