import eventlet
eventlet.monkey_patch()

import asyncio
import sys
from eventlet import tpool

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def my_coro(idx):
    await asyncio.sleep(0.3)
    return f"Done {idx}"

def run_coro_safe(idx):
    def _inner():
        # Inside tpool, we are in a pure OS thread. We can just use asyncio.run()!
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        return asyncio.run(my_coro(idx))
    
    return tpool.execute(_inner)

def test():
    pool = eventlet.GreenPool(size=5)
    print("--- Test tpool with asyncio.run ---")
    for r in pool.imap(run_coro_safe, range(5)):
        print(r)

if __name__ == "__main__":
    test()
