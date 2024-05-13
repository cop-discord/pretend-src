import re
import orjson
import aiohttp
import asyncio
import datetime

from collections import defaultdict
from bs4 import BeautifulSoup
from typing import Optional

from discord.ui import View, Button
from discord.ext.commands import Cog, CooldownMapping, BucketType

from discord import AllowedMentions, Message, MessageType, File, Embed

from tools.bot import Pretend
from tools.exceptions import ApiError
from tools.validators import ValidAutoreact


class Messages(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self._ccd = CooldownMapping.from_cooldown(4, 6, BucketType.channel)
        self.locks = defaultdict(asyncio.Lock)
        self.autoreact_cd = CooldownMapping.from_cooldown(4, 6, BucketType.channel)
        self.testing_server = 1218519366610456626

    async def get_autoreact_cd(self, message: Message) -> Optional[int]:
        """
        custom rate limit for autoreact
        """

        bucket = self.autoreact_cd.get_bucket(message)
        return bucket.update_rate_limit()

    async def get_ratelimit(self, message: Message) -> Optional[int]:
        """
        custom rate limit for reposters
        """

        bucket = self._ccd.get_bucket(message)
        return bucket.update_rate_limit()

    async def repost_instagram(self, message: Message):
        """
        repost an instagram post
        """

        cooldown = await self.get_ratelimit(message)
        if not cooldown:
            async with self.locks[message.guild.id]:
                async with message.channel.typing():
                    url = message.content[len("pretend") + 1 :]
                    try:
                        await message.delete()
                    except:
                        pass

                    if cache := self.bot.cache.get(f"igpost-{url}"):
                        post_data = cache
                    else:
                        headers = {
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1",
                            "Cookie": "_gid=GA1.2.1666878334.1698168914; _gat_UA-174582130-1=1; _ga=GA1.2.865855812.1698168914; _ga_MNQG2TK2HP=GS1.1.1698168913.1.1.1698168919.54.0.0",
                            "X-Requested-With": "XMLHttpRequest",
                        }

                        body = {"url": url, "lang_code": "en"}

                        async with aiohttp.ClientSession(headers=headers) as cs:
                            async with cs.post("https://fastdl.app/c/", data=body) as r:
                                if r.status == 200:
                                    data = await r.read()
                                    soup = BeautifulSoup(data, "html.parser")
                                    post = soup.find("a")

                                    post_data = {
                                        "url": post["href"],
                                        "extension": (
                                            "png"
                                            if post["data-mediatype"] == "Image"
                                            else "mp4"
                                        ),
                                    }

                                    await self.bot.cache.set(
                                        f"igpost-{url}", post_data, 3600
                                    )
                                else:
                                    raise ApiError(r.stauts)

                    view = View()
                    view.add_item(
                        Button(
                            label="post url",
                            url=url,
                            emoji="<:instagram:1051097570753122344>",
                        )
                    )

                    file = File(
                        await self.bot.getbyte(post_data["url"]),
                        filename=f"pretend_instagram.{post_data['extension']}",
                    )
                    return await message.channel.send(file=file, view=view)

    async def repost_tiktok(self, message: Message):
        """
        repost a tiktok
        """

        cooldown = await self.get_ratelimit(message)
        if not cooldown:
            async with self.locks[message.guild.id]:

                url = message.content[len("pretend") + 1 :]
                try:
                    await message.delete()
                except:
                    pass

                async with message.channel.typing():
                    x = await self.bot.session.get_json(
                        "https://tikwm.com/api/", params={"url": url}
                    )
                    if x["data"].get("images"):
                        embeds = []
                        for img in x["data"]["images"]:
                            embed = (
                                Embed(
                                    color=self.bot.color,
                                    description=f"[**Tiktok**]({url}) requested by {message.author}",
                                )
                                .set_author(
                                    name=f"@{x['data']['author']['unique_id']}",
                                    icon_url=x["data"]["author"]["avatar"],
                                    url=url,
                                )
                                .set_footer(
                                    text=f"❤️ {x['data']['digg_count']:,}  💬 {x['data']['comment_count']:,} | {x['data']['images'].index(img)+1}/{len(x['data']['images'])}"
                                )
                                .set_image(url=img)
                            )

                        embeds.append(embed)
                        ctx = await self.bot.get_context(message)
                        return await ctx.paginator(embeds)
                    else:
                        video = x["data"]["play"]
                        file = File(
                            fp=await self.bot.getbyte(video),
                            filename="pretendtiktok.mp4",
                        )
                        embed = Embed(
                            color=self.bot.color,
                            description=(
                                f"[{x['data']['title']}]({url})"
                                if x["data"]["title"]
                                else ""
                            ),
                        ).set_author(
                            name=f"@{x['data']['author']['unique_id']}",
                            icon_url=x["data"]["author"]["avatar"],
                        )
                        x = x["data"]

                        embed.set_footer(
                            text=f"❤️ {x['digg_count']:,}  💬 {x['comment_count']:,}  🔗 {x['share_count']:,}  👀 {x['play_count']:,} | {message.author}"
                        )
                        await message.channel.send(embed=embed, file=file)

    @Cog.listener("on_message")
    async def bump_event(self, message: Message):
        if message.type == MessageType.chat_input_command:
            if (
                message.interaction.name == "bump"
                and message.author.id == 302050872383242240
            ):
                if (
                    "Bump done!" in message.embeds[0].description
                    or "Bump done!" in message.content
                ):
                    check = await self.bot.db.fetchrow(
                        "SELECT thankyou FROM bumpreminder WHERE guild_id = $1",
                        message.guild.id,
                    )
                    if check is not None:
                        x = await self.bot.embed_build.alt_convert(
                            message.interaction.user, check[0]
                        )
                        x["allowed_mentions"] = AllowedMentions.all()
                        await message.channel.send(**x)
                        await self.bot.db.execute(
                            "UPDATE bumpreminder SET time = $1, channel_id = $2, user_id = $3 WHERE guild_id = $4",
                            datetime.datetime.now() + datetime.timedelta(hours=2),
                            message.channel.id,
                            message.interaction.user.id,
                            message.guild.id,
                        )

    @Cog.listener("on_message")
    async def on_boost(self, message: Message):
        if message.guild:
            if "MessageType.premium_guild" in str(message.type):
                if message.guild.id == 1005150492382478377:
                    res = await self.bot.db.fetchrow(
                        "SELECT * FROM donor WHERE user_id = $1", message.author.id
                    )
                    if not res:
                        await self.bot.db.execute(
                            "INSERT INTO donor VALUES ($1,$2,$3)",
                            message.author.id,
                            datetime.datetime.now().timestamp(),
                            "boosted",
                        )

                member = message.author

                results = await self.bot.db.fetch(
                    "SELECT * FROM boost WHERE guild_id = $1", message.guild.id
                )
                for result in results:
                    channel = self.bot.get_channel(result["channel_id"])
                    if channel:
                        perms = channel.permissions_for(member.guild.me)
                        if perms.send_messages and perms.embed_links:
                            x = await self.bot.embed_build.alt_convert(
                                member, result["message"]
                            )
                            await channel.send(**x)
                            await asyncio.sleep(0.4)

    @Cog.listener("on_message")
    async def on_autoresponder(self, message: Message):
        if message.author.bot:
            return

        if not message.guild:
            return

        for row in await self.bot.db.fetch(
            "SELECT * FROM autoresponder WHERE guild_id = $1", message.guild.id
        ):
            if row["strict"] is True:
                if str(row["trigger"]).lower() == message.content.lower():
                    ctx = await self.bot.get_context(message)
                    x = await self.bot.embed_build.convert(ctx, row["response"])

                    await ctx.send(**x)
            else:
                if str(row["trigger"]).lower() in message.content.lower():
                    ctx = await self.bot.get_context(message)
                    x = await self.bot.embed_build.convert(ctx, row["response"])

                    await ctx.send(**x)

    @Cog.listener("on_message")
    async def on_autoreact(self, message: Message):
        if message.author.bot:
            return

        if not message.guild:
            return

        if not message.guild.me.guild_permissions.add_reactions:
            return

        words = message.content.lower().split()
        results = await self.bot.db.fetch(
            "SELECT * FROM autoreact WHERE guild_id = $1", message.guild.id
        )
        for result in results:
            if result["trigger"] in words:
                bucket = await self.get_autoreact_cd(message)

                if bucket:
                    return

                reactions = orjson.loads(result["reactions"])
                ctx = await self.bot.get_context(message)
                for reaction in reactions:
                    x = await ValidAutoreact().convert(ctx, reaction)
                    if x:
                        await message.add_reaction(x)
                return

    @Cog.listener("on_message_delete")
    async def snipes(self, message: Message):
        if message.author.bot:
            return

        get_snipes = self.bot.cache.get("snipe")
        payload = [
            {
                "channel": message.channel.id,
                "name": str(message.author),
                "avatar": message.author.display_avatar.url,
                "message": message.content,
                "attachments": message.attachments,
                "stickers": message.stickers,
                "created_at": message.created_at.timestamp(),
            }
        ]

        if get_snipes:
            lol = self.bot.cache.get("snipe")
            lol.append(
                {
                    "channel": message.channel.id,
                    "name": str(message.author),
                    "avatar": message.author.display_avatar.url,
                    "message": message.content,
                    "attachments": message.attachments,
                    "stickers": message.stickers,
                    "created_at": message.created_at.timestamp(),
                }
            )
            return await self.bot.cache.set("snipe", lol)
        else:
            await self.bot.cache.set("snipe", payload)

    @Cog.listener("on_message_edit")
    async def edit_snipe(self, before: Message, after: Message):
        if before.author.bot:
            return
        if before.content == after.content:
            return

        get_snipes = self.bot.cache.get("edit_snipe")
        if get_snipes:
            lol = self.bot.cache.get("edit_snipe")
            lol.append(
                {
                    "channel": before.channel.id,
                    "name": str(before.author),
                    "avatar": before.author.display_avatar.url,
                    "before": before.content,
                    "after": after.content,
                }
            )
            return await self.bot.cache.set("edit_snipe", lol)
        else:
            payload = [
                {
                    "channel": before.channel.id,
                    "name": str(before.author),
                    "avatar": before.author.display_avatar.url,
                    "before": before.content,
                    "after": after.content,
                }
            ]
            return await self.bot.cache.set("edit_snipe", payload)

    @Cog.listener("on_message")
    async def reposter(self, message: Message):
        if (
            message.guild
            and not message.author.bot
            and message.content.startswith("pretend")
        ):
            if re.search(
                r"\bhttps?:\/\/(?:m|www|vm)\.tiktok\.com\/\S*?\b(?:(?:(?:usr|v|embed|user|video)\/|\?shareId=|\&item_id=)(\d+)|(?=\w{7})(\w*?[A-Z\d]\w*)(?=\s|\/$))\b",
                message.content[len("pretend") + 1 :],
            ):
                return await self.repost_tiktok(message)
            elif re.search(
                r"((?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:p|reel)\/([^/?#&]+)).*",
                message.content[len("pretend") + 1 :],
            ):
                return await self.repost_instagram(message)

    @Cog.listener("on_message")
    async def imageonly_check(self, message: Message):

        if message.guild is None:
            return
        if not message.guild.me.guild_permissions.manage_messages:
            return

        if await self.bot.db.fetchrow(
            """
       SELECT * FROM imgonly
       WHERE guild_id = $1
       AND channel_id = $2
       """,
            message.guild.id,
            message.channel.id,
        ):
            if not message.author.guild_permissions.manage_messages:
                cooldown = await self.get_ratelimit(message)
                if not message.attachments:
                    await message.delete()


async def setup(bot) -> None:
    return await bot.add_cog(Messages(bot))
