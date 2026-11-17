import asyncio

_alive: set = set()


def spawn(coro):
    """create_task that keeps a reference (asyncio only holds weak references, so a bare create_task can be
    garbage-collected mid-run) and reports unexpected errors instead of swallowing them."""
    task = asyncio.get_running_loop().create_task(coro)
    _alive.add(task)

    def done(t):
        _alive.discard(t)
        if not t.cancelled() and t.exception() is not None:
            from .log import log
            log(f"background task failed: {type(t.exception()).__name__}: {t.exception()}")
    task.add_done_callback(done)
    return task
