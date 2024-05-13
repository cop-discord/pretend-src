from types import ModuleType
from typing import Coroutine, Callable, Any, DefaultDict, TypeVar, Optional, Union, AsyncGenerator, Awaitable
from collections import defaultdict
from asyncio import Lock, sleep, to_thread, wait_for, ensure_future, gather
import traceback
from datetime import datetime, timedelta
from functools import wraps, partial
from contextlib import asynccontextmanager
from tuuid import tuuid
from cashews.keys import get_cache_key as _get_cache_key
from cashews._typing import KeyOrTemplate
from dataclasses import dataclass
from loguru import logger

GLOBALS = {}
T = TypeVar("T")
AsyncCallableResult_T = TypeVar("AsyncCallableResult_T")
AsyncCallable_T = Callable[..., Awaitable[AsyncCallableResult_T]]
DecoratedFunc = TypeVar("DecoratedFunc", bound=AsyncCallable_T)
rl = discord.ExpiringDictionary()

def get_ts(sec: int = 0):
    ts = datetime.now() + timedelta(seconds = sec)
    return int(ts.timestamp())

def get_cache_key(key: KeyOrTemplate, func: DecoratedFunc, *args, **kwargs):
    return _get_cache_key(func, key, args, kwargs)

def get_logger():
    return logger

METHOD_LOCKERS = {}

@dataclass
class Timer:
    start: float
    end: Optional[float] = None
    elapsed: Optional[float] = None

@asynccontextmanager
async def timeit():
    start = datetime.now().timestamp()
    timer = Timer(start = start)
    try:
        yield timer
    finally:
        end = datetime.now().timestamp()
        elapsed = end - start
        timer.end = end
        timer.elapsed = elapsed

def lock(key: KeyOrTemplate, wait=True):
    """ In order to share memory between any asynchronous coroutine methods, we should use locker to lock our method,
        so that we can avoid some un-prediction actions.

    Args:
        name: Locker name.
        wait: If waiting to be executed when the locker is locked? if True, waiting until to be executed, else return
            immediately (do not execute).

    NOTE:
        This decorator must to be used on `async method`.
    """
    assert isinstance(key, str)

    def decorating_function(func: DecoratedFunc) -> DecoratedFunc:
        global METHOD_LOCKERS
        @wraps(func)
        async def wrapper(*args, **kwargs):
            value = get_cache_key(key, func, *args, **kwargs)
            locker = METHOD_LOCKERS.get(value)
            if not locker:
                locker = Lock()
                METHOD_LOCKERS[value] = locker
            if not wait and locker.locked():
                return
            try:
                await locker.acquire()
                return await func(*args, **kwargs)
            finally:
                locker.release()
        return wrapper
    return decorating_function

def thread(func: Callable):
    """Asynchronously run function `func` in a separate thread"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        coro = to_thread(func, *args, **kwargs)
        return await coro

    return wrapper

