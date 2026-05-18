#!/usr/bin/env python3
"""
Layer 4 — Background worker (Redis queue consumer).

Usage:
  cd backend && python ../scripts/run_worker.py

Scales horizontally: run multiple instances for autoscaling workers.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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
