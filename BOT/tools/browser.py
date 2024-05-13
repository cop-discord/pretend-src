from playwright.async_api import async_playwright, Page, request
from typing import Optional, List, Kwargs, Args
from typing_extensions import Self
from cashews import cache
from contextlib import suppress
from functools import wraps
import numpy as np, cv2
from io import BytesIO
from discord.ext.commands import CommandError
from tools import Lock
from nudenet import NudeDetector
from asyncio import ensure_future, sleep, iscoroutinefunction as is_coroutine
try:
    from async_timeout import timeout
except:
    try:
        from async_timeout import Timeout as timeout
    except:
        from async_timeout import TimeOut as timeout
from xxhash import xxh3_64_hexdigest as hash_

def is_initialized():
    def decorator(func):
        def check(*args):
            if not hasattr(args[0], "playwright"):
                raise AttributeError("Browser hasn't been Initialized")
            return
        @wraps(func)
        async def wrapper(*args, **kwargs):
            check(args)
            return await func(*args, **kwargs)
        def wrapper_(*args, **kwargs):
            check(args)
            return func(*args, **kwargs)
        if is_coroutine(func):
            return wrapper
        else:
            return wrapper_
    return decorator

cache.setup("mem://")

class Browser:
    def __init__(self, bot):
        self.bot = bot
        self.pages = dict()
        self.nudity_detector = NudeDetector()
        self.explicit = {
            "FEMALE_BREAST_EXPOSED",
            "ANUS_EXPOSED",
            "FEMALE_GENITALIA_EXPOSED",
            "MALE_GENITALIA_EXPOSED",
            "BUTTOCKS_EXPOSED",
        }

    async def initialize(self: Self, *args: Args, **kwargs: Kwargs) -> None:
        async def launch(*args, **kwargs):
            with suppress(FileExistsError):
                # This fixes a rare exception that gets raised when tmp gets auto deleted and playwright can't launch
				os.mkdir('/tmp')
            logger.info("Initializing Browser..")
            self.playwright = await async_playwright().start()
            self.session = await self.playwright.chromium.launch(*args, **kwargs)
            logger.info("Browser successfully initialized")
            return
        return await ensure_future(launch(args, kwargs))
    
    async def create_page(self: Self, **kwargs: Kwargs) -> Page:
        for page, options in self.pages.items():
            if options["kwargs"] == f"{kwargs}":
                if options["status"] == False:
                    self.pages[page] = True
                    return page
        context = await self.browser.new_context(java_script_enabled=True, **kwargs)
        page = await context.new_page()
        await stealth_async(page)
        self.pages[page] = {"status": True, "kwargs": f"{kwargs}"}
        return page
    
    @thread
    def check_content(self: Self, screenshot: BytesIO) -> None:
        image_data = screenshot.read()
        image = np.frombuffer(image_data, np.uint8)
        detections = self.nudity_detector.detect(image)
        if any(prediction["class"] in self.explicit for prediction in detections):
            raise CommandError(f"This screenshot is NSFW please enable NSFW on the channel")
        return

    async def change_status(self: Self, page: Page) -> None:
        self.pages[page]["status"] = False
        return

    
    @lock(f"screenshot:{url}")
    async def screenshot(self: Self, url: str, **kwargs: Kwargs) -> Optional[BytesIO]:
        if not validators.url(url):
            raise CommandError(f"Invalid URL")
        nsfw = kwargs.get("is_nsfw", False)
        wait_for = kwargs.get("wait_for", "networkidle")
        full_page = kwargs.get("full_page", False)
        wait = kwargs.get("wait", None)
        key = hash_(f"{url}-{kwargs}")
        if screenshot := self.cache.get(key):
            pass
        else:
            page = await self.create_page()
            async with timeout(20):
                kw = {"url": url, "wait_for": wait_for, "full_page": full_page}
                await page.goto(**kw)
                if wait != None:
                    await sleep(wait)
                screenshot = BytesIO(await page.screenshot(animations='disabled', full_page=full_page))
            if "ip" in str(await page.content()).lower():
                raise CommandError(f"Nice try")
        if nsfw == False:
            await self.check_content(screenshot)
        self.cache[key] = screenshot
        return screenshot
            







