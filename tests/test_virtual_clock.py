import asyncio
import time

import pytest


@pytest.mark.virtual_clock
async def test_the_clock_waits_for_a_thread_job_instead_of_skipping_ahead():
    job = asyncio.get_running_loop().run_in_executor(None, time.sleep, 0.1)

    await asyncio.wait_for(job, timeout=60)


@pytest.mark.virtual_clock
async def test_the_clock_waits_for_the_executor_shutdown():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, int)

    await asyncio.wait_for(loop.shutdown_default_executor(), timeout=60)
