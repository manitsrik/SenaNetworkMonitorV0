"""
Compatibility layer for cooperative runtime helpers.

This keeps the current Eventlet-based behavior in one place so the rest of
the codebase can migrate incrementally later.
"""
import sys
import warnings

with warnings.catch_warnings():
    warnings.simplefilter('ignore', DeprecationWarning)
    import eventlet
    from eventlet import tpool as _eventlet_tpool
    from eventlet.timeout import Timeout as _EventletTimeout


ASYNC_RUNTIME = 'eventlet'
RUNTIME_LABEL = 'eventlet (compat)'
GreenPool = eventlet.GreenPool
Timeout = _EventletTimeout
TimeoutError = _EventletTimeout

_MONKEY_PATCHED = False


def monkey_patch(all=True):
    global _MONKEY_PATCHED
    if not _MONKEY_PATCHED:
        eventlet.monkey_patch(all=all)
        _MONKEY_PATCHED = True


def configure_asyncio_policy():
    if sys.platform == 'win32':
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def spawn(func, *args, **kwargs):
    return eventlet.spawn(func, *args, **kwargs)


def sleep(seconds=0):
    return eventlet.sleep(seconds)


def tpool_execute(func, *args, **kwargs):
    return _eventlet_tpool.execute(func, *args, **kwargs)
