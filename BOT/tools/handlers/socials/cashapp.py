import aiohttp

from typing import Any
from pydantic import BaseModel
from discord.ext import commands
from tools.helpers import PretendContext


class CashApp(BaseModel):
    """
    Model for cashapp user
    """

    url: str
    qr: Any


class CashappUser(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str) -> CashApp:
        async with aiohttp.ClientSession() as cs:
            async with cs.get(f"https://cash.app/${argument}") as r:
                if r.status == 404:
                    raise commands.BadArgument("Cashapp profile not found")
                if r.status == 200:
                    data = {
                        "url": str(r.url),
                        "qr": await ctx.bot.getbyte(
                            f"https://cash.app/qr/${argument}?size=288&margin=0"
                        ),
                    }
                    return CashApp(**data)
                else:
                    raise commands.BadArgument(
                        "There was a problem getting the user's cashapp profile"
                    )
