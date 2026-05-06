from redis import Redis
from rq import Queue, Worker

from app.config import settings


def main() -> None:
    redis = Redis.from_url(settings.redis_url)
    queue = Queue("default", connection=redis)
    worker = Worker([queue], connection=redis)
    worker.work()


if __name__ == "__main__":
    main()

