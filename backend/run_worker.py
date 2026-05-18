"""Redis queue worker entrypoint (Layer 4). Run: python run_worker.py"""
import asyncio

from app.core.logging import configure_logging
from app.workers.queue import dequeue
from app.workers.tasks import handle_job

configure_logging()


async def main():
    print("AI Calling Agent worker started — waiting for jobs...")
    while True:
        job = await dequeue(timeout=5)
        if job:
            try:
                await handle_job(job)
            except Exception as e:
                print(f"Job failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
