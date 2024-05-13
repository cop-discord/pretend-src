import aiohttp

from typing import Optional
from pydantic import BaseModel
from discord.ext import commands
from tools.helpers import PretendContext


class Snapchat(BaseModel):
    """
    Model for snapchat profile
    """

    username: str
    display_name: str
    snapcode: str
    bio: Optional[str]
    avatar: str
    url: str


class SnapUser(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str) -> Snapchat:
        async with aiohttp.ClientSession(
            headers={"api-key": ctx.bot.pretend_api}
        ) as cs:
            async with cs.get(
                "https://v1.pretend.best/snapchat", params={"username": argument}
            ) as r:
                if r.status != 200:
                    raise commands.BadArgument(
                        f"Couldn't get information about **{argument}**"
                    )

                return Snapchat(**(await r.json()))
