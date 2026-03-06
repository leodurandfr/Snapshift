import asyncio
import logging

from app.worker.runner import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    worker = Worker()
    asyncio.run(worker.start())


if __name__ == "__main__":
    main()
