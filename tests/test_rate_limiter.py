import asyncio

import pytest

from lumibot.gmgn.client import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_releases_lock_while_waiting():
    lim = RateLimiter(capacity=1, refill_per_sec=2)
    await lim.acquire(1)

    async def waiter():
        await lim.acquire(1)

    t = asyncio.create_task(waiter())
    await asyncio.sleep(0.02)  # waiter should be sleeping outside the lock
    try:
        await asyncio.wait_for(lim._lock.acquire(), timeout=0.05)
        lim._lock.release()
        lock_free = True
    except asyncio.TimeoutError:
        lock_free = False
    await t
    assert lock_free, "RateLimiter must not hold the lock while sleeping"
