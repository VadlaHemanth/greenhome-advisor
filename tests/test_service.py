import asyncio
import threading

import pytest

from greenhome.security import ServiceBusy
from greenhome.service import CalculationService, integer_setting


def test_many_requests_queued_within_bound():
    async def run():
        service = CalculationService(2, 128)
        try:
            values = await asyncio.gather(*(
                service.run(lambda x: x * x, i) for i in range(100)
            ))
            assert values == [i * i for i in range(100)]
            assert service.pending == 0
        finally:
            service.close()
    asyncio.run(run())


def test_deadline_does_not_release_running_job():
    release = threading.Event()
    entered = threading.Event()
    def slow():
        entered.set()
        release.wait(3)

    async def run():
        service = CalculationService(1, 1)
        try:
            with pytest.raises(ServiceBusy):
                await service.run(slow, timeout=.02)
            assert entered.is_set()
            assert service.pending == 1
            with pytest.raises(ServiceBusy):
                await service.run(lambda: None)
            release.set()
            for _ in range(100):
                if service.pending == 0:
                    break
                await asyncio.sleep(.01)
            assert service.pending == 0
        finally:
            release.set()
            service.close()
    asyncio.run(run())


def test_cancelled_waiter_keeps_running_slot():
    release = threading.Event()
    entered = threading.Event()
    def slow():
        entered.set()
        release.wait(3)
    async def run():
        service = CalculationService(1, 1)
        task = asyncio.create_task(service.run(slow))
        try:
            while not entered.is_set():
                await asyncio.sleep(.001)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert service.pending == 1
        finally:
            release.set()
            service.close()
    asyncio.run(run())


def test_closed_service_rejects_without_background_jobs():
    async def run():
        service = CalculationService()
        service.close()
        with pytest.raises(ServiceBusy):
            await service.run(lambda: True)
        assert service.pending == 0
    asyncio.run(run())


def test_configuration_is_bounded(monkeypatch):
    monkeypatch.setenv("CAPACITY_TEST", "not-an-integer")
    with pytest.raises(RuntimeError):
        integer_setting("CAPACITY_TEST", 4, 1, 8)
    monkeypatch.setenv("CAPACITY_TEST", "9")
    with pytest.raises(RuntimeError):
        integer_setting("CAPACITY_TEST", 4, 1, 8)
