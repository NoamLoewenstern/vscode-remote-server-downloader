from os import PathLike
from pathlib import Path
from typing import Union
from functools import wraps
import aiohttp
import asyncio

StrPath = Union[str, PathLike[str]]

def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        return asyncio.run(f(*args, **kwargs))

    return wrapper


async def download_file(session: aiohttp.ClientSession, url: str, dst_file: StrPath):
    chunk_size = 1024 * 1024  # 1MB
    dst_file = Path(dst_file)
    print(f'downloading {url} to: {str(dst_file)}')
    async with session.get(url) as resp:
        with dst_file.open('wb') as fh:
            while True:
                chunk = await resp.content.read(chunk_size)
                if not chunk:
                    print(f'finished downloading {str(dst_file)}')
                    break
                fh.write(chunk)
