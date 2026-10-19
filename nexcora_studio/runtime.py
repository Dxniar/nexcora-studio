"""Psycopg async requires a selector loop on Windows."""
import asyncio
import sys
from contextlib import suppress


def loop_factory():
    return asyncio.SelectorEventLoop() if sys.platform == 'win32' else asyncio.new_event_loop()


async def blocking(function, *args):
    """Finish bounded I/O before cancellation releases its temporary files."""
    operation = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(operation)
    except asyncio.CancelledError:
        with suppress(Exception): await operation
        raise
