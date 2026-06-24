"""Queue abstraction (M1): in-process or RQ/Redis, selected by config.

- ``inprocess`` runs the job synchronously in the caller. Perfect for the local
  demo and tests: upload returns once the invoice has been fully processed, so the
  API and UI are immediately consistent.
- ``redis`` enqueues onto RQ; a separate ``rq worker`` process consumes it (the
  docker-compose path).
"""

from __future__ import annotations

from functools import lru_cache

from .config import get_settings


class InProcessQueue:
    backend = "inprocess"

    def enqueue(self, invoice_id: str) -> None:
        from .worker import run_job

        run_job(invoice_id)


class RedisQueue:
    backend = "redis"

    def __init__(self) -> None:
        from redis import Redis
        from rq import Queue

        settings = get_settings()
        self._queue = Queue("ledgerflow", connection=Redis.from_url(settings.redis_url))

    def enqueue(self, invoice_id: str) -> None:
        # reference the task by string path so the worker process can import it
        self._queue.enqueue("app.worker.run_job", invoice_id)


@lru_cache
def get_queue():
    settings = get_settings()
    if settings.queue_backend == "redis":
        return RedisQueue()
    return InProcessQueue()
