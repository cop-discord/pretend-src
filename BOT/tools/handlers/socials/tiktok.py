import aiohttp

from pydantic import BaseModel
from discord.ext import commands
from typing import List, Optional
from tools.helpers import PretendContext


class TikTok(BaseModel):
    """
    Model for tiktok user
    """

    username: str
    nickname: Optional[str]
    avatar: str
    bio: str
    badges: List[str]
    url: str
    followers: int
    following: int
    hearts: int


class TikTokUser(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str) -> TikTok:
        async with ctx.typing():
            async with aiohttp.ClientSession(
                headers={"api-key": ctx.bot.pretend_api}
            ) as cs:
                async with cs.get(
                    "https://v1.pretend.best/tiktok", params={"username": argument}
                ) as r:
                    if r.status != 200:
                        raise commands.BadArgument("Couldn't get this tiktok page")

                    data = await r.json()
                    badges = []

                    if data.get("private"):
                        badges.append("🔒")

                    if data.get("verified"):
                        badges.append("<:verified:1111747172677988373>")

                    data["badges"] = badges
                    return TikTok(**data)
