"""Worker entrypoint.

Two modes, chosen by config:

- ``LEDGERFLOW_QUEUE_BACKEND=redis`` : run an RQ worker consuming the ``ledgerflow``
  queue (the docker-compose path). The folder watcher runs in a background thread
  and enqueues onto the same queue.
- otherwise : run only the folder watcher; jobs execute in-process as files arrive.
"""

from __future__ import annotations

import threading

from app.config import get_settings
from app.db import init_db
from app.ingest.watcher import watch_folder
from app.seed import seed_known_vendors


def main() -> None:
    init_db()
    seed_known_vendors()
    settings = get_settings()

    if settings.queue_backend == "redis":
        from redis import Redis
        from rq import Queue, Worker

        # folder watcher in a daemon thread; it enqueues onto Redis.
        threading.Thread(target=watch_folder, daemon=True).start()

        conn = Redis.from_url(settings.redis_url)
        worker = Worker([Queue("ledgerflow", connection=conn)], connection=conn)
        print("[worker] RQ worker started, consuming 'ledgerflow' queue")
        worker.work(with_scheduler=True)
    else:
        # in-process: the watcher both ingests and runs the job synchronously.
        watch_folder()


if __name__ == "__main__":
    main()
