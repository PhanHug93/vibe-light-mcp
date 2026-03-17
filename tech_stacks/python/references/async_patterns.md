# Python — Async Patterns Deep Dive

## Core Concepts

### Event Loop & Coroutines

```python
import asyncio

# Modern entry point (Python 3.10+)
async def main() -> None:
    result = await fetch_data()
    print(result)

asyncio.run(main())  # ✅ Only call from sync context

# ❌ NEVER do this in async context:
# loop = asyncio.get_event_loop()
# loop.run_until_complete(coro)
```

### TaskGroup (Python 3.11+ — Structured Concurrency)

```python
async def fetch_all_data() -> tuple[list[User], list[Order]]:
    """Run multiple async operations concurrently with error propagation."""
    async with asyncio.TaskGroup() as tg:
        users_task = tg.create_task(fetch_users())
        orders_task = tg.create_task(fetch_orders())

    # All tasks completed or all cancelled on first exception
    return users_task.result(), orders_task.result()
```

### gather vs TaskGroup

```python
# gather — legacy, less safe (exceptions can be swallowed)
results = await asyncio.gather(
    fetch_users(),
    fetch_orders(),
    return_exceptions=True,  # ⚠ hides exceptions in results
)

# TaskGroup — preferred (Python 3.11+)
# ✅ Proper exception propagation
# ✅ Automatic cancellation of remaining tasks on error
# ✅ Structured concurrency
```

## Rate Limiting & Concurrency Control

### Semaphore

```python
MAX_CONCURRENT = 10
sem = asyncio.Semaphore(MAX_CONCURRENT)

async def rate_limited_fetch(url: str) -> dict:
    async with sem:  # At most MAX_CONCURRENT coroutines here
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            return resp.json()

async def fetch_many(urls: list[str]) -> list[dict]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(rate_limited_fetch(url)) for url in urls]
    return [t.result() for t in tasks]
```

### BoundedSemaphore (safer — raises on over-release)

```python
sem = asyncio.BoundedSemaphore(5)
# Raises ValueError if released more than acquired
```

## Timeout Patterns

```python
# asyncio.timeout (Python 3.11+)
async def fetch_with_timeout(url: str) -> dict:
    async with asyncio.timeout(30):
        return await fetch(url)  # Raises TimeoutError after 30s

# asyncio.wait_for (older, still valid)
try:
    result = await asyncio.wait_for(slow_operation(), timeout=10.0)
except asyncio.TimeoutError:
    logger.warning("Operation timed out")
    result = default_value

# Nested timeouts — inner wins
async with asyncio.timeout(60):         # outer: 60s total
    data = await fetch_data()            # may use some time
    async with asyncio.timeout(10):      # inner: 10s for processing
        result = await process(data)
```

## Cancellation Handling

```python
async def cancellable_worker(queue: asyncio.Queue) -> None:
    try:
        while True:
            item = await queue.get()
            await process(item)
            queue.task_done()
    except asyncio.CancelledError:
        logger.info("Worker cancelled, cleaning up...")
        # ✅ Always cleanup on cancellation
        await flush_pending()
        raise  # ✅ Re-raise to properly propagate cancellation

# Shielding from cancellation (use sparingly)
async def critical_operation() -> None:
    # This will complete even if outer task is cancelled
    result = await asyncio.shield(save_to_database(data))
```

## Producer-Consumer Pattern

```python
async def producer(queue: asyncio.Queue[str]) -> None:
    for url in get_urls():
        await queue.put(url)
    # Signal consumers to stop
    for _ in range(NUM_WORKERS):
        await queue.put(None)  # sentinel

async def consumer(queue: asyncio.Queue[str], results: list) -> None:
    while True:
        url = await queue.get()
        if url is None:
            break
        result = await fetch(url)
        results.append(result)
        queue.task_done()

async def run_pipeline() -> list:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    results: list = []
    async with asyncio.TaskGroup() as tg:
        tg.create_task(producer(queue))
        for _ in range(NUM_WORKERS):
            tg.create_task(consumer(queue, results))
    return results
```

## Blocking I/O in Async Context

```python
import asyncio
from pathlib import Path

# ❌ Blocks the event loop
async def bad_read() -> str:
    return Path("large_file.txt").read_text()

# ✅ Run in thread pool
async def good_read() -> str:
    return await asyncio.to_thread(Path("large_file.txt").read_text)

# ✅ Custom executor for CPU-bound work
from concurrent.futures import ProcessPoolExecutor

async def cpu_intensive(data: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor() as pool:
        return await loop.run_in_executor(pool, heavy_compute, data)
```

## Connection Management

```python
import httpx

# ✅ Reuse client (connection pooling)
class ApiService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.example.com",
            timeout=30.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_user(self, user_id: str) -> dict:
        resp = await self._client.get(f"/users/{user_id}")
        resp.raise_for_status()
        return resp.json()

# ❌ Creating new client per request
async def bad_fetch(url: str) -> dict:
    async with httpx.AsyncClient() as client:  # New connection each time!
        return (await client.get(url)).json()
```

## Anti-patterns ❌

- `asyncio.get_event_loop()` — deprecated, dùng `asyncio.get_running_loop()`
- `loop.run_until_complete()` trong async context
- Blocking calls (file I/O, `time.sleep()`) trong coroutine
- Fire-and-forget tasks không track — dùng `TaskGroup` hoặc keep reference
- `asyncio.gather(return_exceptions=True)` rồi không check exceptions
- Không handle `CancelledError` → resource leaks
- Tạo quá nhiều tasks không giới hạn → dùng Semaphore
