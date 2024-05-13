import discord, datetime, io

from discord.ext.commands import Cog
from tools.bot import Pretend


class Reactions(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot

    # reaction roles

    @Cog.listener("on_raw_reaction_add")
    async def on_reactionrole_add(self, payload: discord.RawReactionActionEvent):
        m = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
        if not m:
            return
        if m.bot:
            return

        check = await self.bot.db.fetchrow(
            "SELECT role_id FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
            str(payload.emoji),
        )
        if check:
            role = self.bot.get_guild(payload.guild_id).get_role(check[0])
            if role:
                if role.is_assignable():
                    if (
                        not role
                        in self.bot.get_guild(payload.guild_id)
                        .get_member(payload.user_id)
                        .roles
                    ):
                        await self.bot.get_guild(payload.guild_id).get_member(
                            payload.user_id
                        ).add_roles(role, reason="Reaction Role")

    @Cog.listener("on_raw_reaction_remove")
    async def on_reactionrole_remove(self, payload: discord.RawReactionActionEvent):
        m = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
        if not m:
            return
        if m.bot:
            return

        check = await self.bot.db.fetchrow(
            "SELECT role_id FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
            str(payload.emoji),
        )
        if check:
            role = self.bot.get_guild(payload.guild_id).get_role(check[0])
            if role:
                if role.is_assignable():
                    if (
                        role
                        in self.bot.get_guild(payload.guild_id)
                        .get_member(payload.user_id)
                        .roles
                    ):
                        await self.bot.get_guild(payload.guild_id).get_member(
                            payload.user_id
                        ).remove_roles(role, reason="Reaction Role")

    # starboard

    @Cog.listener("on_raw_reaction_remove")
    async def on_starboard_remove(self, payload: discord.RawReactionActionEvent):
        res = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", payload.guild_id
        )
        if res:
            if not res["emoji"]:
                return
            if str(payload.emoji) == res["emoji"]:
                mes = await self.bot.get_channel(payload.channel_id).fetch_message(
                    payload.message_id
                )
                reactions = [
                    r.count for r in mes.reactions if str(r.emoji) == res["emoji"]
                ]
                if len(reactions) > 0:
                    reaction = reactions[0]
                    if not res["channel_id"]:
                        return
                    channel = self.bot.get_channel(res["channel_id"])
                    if channel:
                        check = await self.bot.db.fetchrow(
                            "SELECT * FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                            payload.guild_id,
                            payload.channel_id,
                            payload.message_id,
                        )
                        if check:
                            try:
                                m = await channel.fetch_message(
                                    check["starboard_message_id"]
                                )
                                await m.edit(
                                    content=f"{payload.emoji} **#{reaction}** {mes.channel.mention}"
                                )
                            except:
                                await self.bot.db.execute(
                                    "DELETE FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                                    payload.guild_id,
                                    payload.channel_id,
                                    payload.message_id,
                                )

    @Cog.listener("on_raw_reaction_add")
    async def on_starboard_add(self, payload: discord.RawReactionActionEvent):
        res = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", payload.guild_id
        )
        if res:
            if not res["emoji"]:
                return
            if str(payload.emoji) == res["emoji"]:
                mes = await self.bot.get_channel(payload.channel_id).fetch_message(
                    payload.message_id
                )
                reactions = [
                    r.count for r in mes.reactions if str(r.emoji) == res["emoji"]
                ]
                if len(reactions) > 0:
                    reaction = reactions[0]
                    if not res["channel_id"]:
                        return
                    channel = self.bot.get_channel(res["channel_id"])

                    if not channel:
                        return

                    if payload.channel_id == channel.id:
                        return

                    check = await self.bot.db.fetchrow(
                        "SELECT * FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                        payload.guild_id,
                        payload.channel_id,
                        payload.message_id,
                    )
                    if not check:
                        if not res["count"]:
                            return
                        if reaction < res["count"]:
                            return
                        file = None
                        if not mes.embeds:
                            embed = discord.Embed(
                                color=self.bot.color,
                                description=mes.content,
                                timestamp=mes.created_at,
                            )
                            embed.set_author(
                                name=str(mes.author),
                                icon_url=mes.author.display_avatar.url,
                            )
                            if mes.attachments:
                                if mes.attachments[0].filename.endswith(
                                    ("png", "jpeg", "jpg")
                                ):
                                    embed.set_image(url=mes.attachments[0].proxy_url)
                                elif mes.attachments[0].filename.endswith(
                                    ("mp3", "mp4", "mov")
                                ):
                                    file = discord.File(
                                        fp=io.BytesIO(await mes.attachments[0].read()),
                                        filename=mes.attachments[0].filename,
                                    )
                        else:
                            em = mes.embeds[0]
                            embed = discord.Embed(
                                color=em.color,
                                description=em.description or mes.content,
                                title=em.title,
                                url=em.url,
                            )

                            if em.author:
                                embed.set_author(
                                    name=em.author.name,
                                    icon_url=em.author.proxy_icon_url,
                                    url=em.author.url,
                                )
                            else:
                                embed.set_author(
                                    name=mes.author,
                                    icon_url=mes.author.display_avatar.url,
                                )

                            if em.thumbnail:
                                embed.set_thumbnail(url=em.thumbnail.proxy_url)

                            if em.image:
                                embed.set_image(url=em.image.proxy_url)

                            if em.footer:
                                embed.set_footer(
                                    text=em.footer.text, icon_url=em.footer.icon_url
                                )

                            if mes.attachments:
                                file = discord.File(
                                    fp=io.BytesIO(await mes.attachments[0].read()),
                                    filename=mes.attachments[0].filename,
                                )

                        if mes.reference:
                            embed.description = f"{embed.description}\n<:right:1106622898489262170> [replying to {mes.reference.resolved.author}]({mes.reference.resolved.jump_url})"

                        view = discord.ui.View()
                        view.add_item(
                            discord.ui.Button(label="message", url=mes.jump_url)
                        )
                        perms = channel.permissions_for(channel.guild.me)
                        if (
                            perms.send_messages
                            and perms.embed_links
                            and perms.attach_files
                        ):
                            m = await channel.send(
                                content=f"{payload.emoji} **#{reaction}** {mes.channel.mention}",
                                embed=embed,
                                view=view,
                                file=file,
                            )
                            await self.bot.db.execute(
                                "INSERT INTO starboard_messages VALUES ($1,$2,$3,$4)",
                                payload.guild_id,
                                payload.channel_id,
                                payload.message_id,
                                m.id,
                            )
                    else:
                        try:
                            m = await channel.fetch_message(
                                check["starboard_message_id"]
                            )
                            await m.edit(
                                content=f"{payload.emoji} **#{reaction}** {mes.channel.mention}"
                            )
                        except:
                            await self.bot.db.execute(
                                "DELETE FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                                payload.guild_id,
                                payload.channel_id,
                                payload.message_id,
                            )

    @Cog.listener("on_reaction_remove")
    async def reaction_snipe_event(
        self, reaction: discord.Reaction, user: discord.Member
    ):
        if user.bot:
            return

        get_snipe = self.bot.cache.get("reaction_snipe")
        if get_snipe:
            lol = get_snipe
            lol.append(
                {
                    "channel": reaction.message.channel.id,
                    "message": reaction.message.id,
                    "reaction": str(reaction.emoji),
                    "user": str(user),
                    "created_at": datetime.datetime.now().timestamp(),
                }
            )
            await self.bot.cache.set("reaction_snipe", lol)
        else:
            payload = [
                {
                    "channel": reaction.message.channel.id,
                    "message": reaction.message.id,
                    "reaction": str(reaction.emoji),
                    "user": str(user),
                    "created_at": datetime.datetime.now().timestamp(),
                }
            ]
            await self.bot.cache.set("reaction_snipe", payload)


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Reactions(bot))
