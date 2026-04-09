import async_runtime
async_runtime.monkey_patch()

import asyncio
import sys
if sys.platform == 'win32':
    async_runtime.configure_asyncio_policy()

async def my_coro(idx):
    await asyncio.sleep(0.3)
    return f"Done {idx}"

def run_coro_safe(idx):
    def _inner():
        # Inside the worker thread, we can safely use asyncio.run().
        if sys.platform == 'win32':
            async_runtime.configure_asyncio_policy()
        return asyncio.run(my_coro(idx))
    
    return async_runtime.tpool_execute(_inner)

def test():
    pool = async_runtime.GreenPool(size=5)
    print("--- Test tpool with asyncio.run ---")
    for r in pool.imap(run_coro_safe, range(5)):
        print(r)

if __name__ == "__main__":
    test()
