import aiohttp
from typing import Optional


class Session:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36"
        }

    async def post_json(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        proxy: Optional[str] = None,
    ):
        """
        Use the post method to get the json response
        """

        async with aiohttp.ClientSession(headers=headers or self.headers) as cs:
            async with cs.post(url, headers=headers, params=params, proxy=proxy) as r:
                return await r.json()

    async def get_json(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        proxy: Optional[str] = None,
    ):
        """
        Use the get method to get the json response
        """

        async with aiohttp.ClientSession(headers=headers or self.headers) as cs:
            async with cs.get(url, headers=headers, params=params, proxy=proxy) as r:
                return await r.json()

    async def get_text(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        proxy: Optional[str] = None,
    ):
        """
        Use the get method to get the text response
        """

        async with aiohttp.ClientSession(headers=headers or self.headers) as cs:
            async with cs.get(url, headers=headers, params=params, proxy=proxy) as r:
                return await r.text()

    async def get_bytes(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        proxy: Optional[str] = None,
    ):
        """
        Use the get method to get the bytes response
        """

        async with aiohttp.ClientSession(headers=headers or self.headers) as cs:
            async with cs.get(url, headers=headers, params=params, proxy=proxy) as r:
                return await r.read()
