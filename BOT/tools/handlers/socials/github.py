import aiohttp
import dateutil.parser

from discord.ext import commands

from pydantic import BaseModel
from typing import Optional, Any
from tools.helpers import PretendContext


class Github(BaseModel):
    """
    Model for github user
    """

    username: str
    avatar_url: str
    url: str
    display: str
    company: Optional[str]
    bio: str
    repos: int
    followers: int
    following: int
    created_at: Any


class GithubUser(commands.Converter):
    async def convert(self, ctx: PretendContext, argument: str) -> Github:

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession(headers=headers) as cs:
            async with cs.get(f"https://api.github.com/users/{argument}") as r:
                if r.status != 200:
                    raise commands.BadArgument(
                        "Something went wrong while trying to get this github user"
                    )

                res = await r.json()

                if not res.get("login"):
                    raise commands.BadArgument(
                        f"Github user **{argument}** doesn't exist"
                    )

                res["created_at"] = dateutil.parser.parse(res["created_at"])
                res["repos"] = res["public_repos"]
                res["display"] = res["name"]
                res["username"] = res["login"]
                res["url"] = res["html_url"]
                return Github(**res)
