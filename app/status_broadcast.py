import asyncio
import threading


Subscriber = tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]


class StatusBroadcaster:
    """Broadcast status changes from any thread to async subscribers."""

    def __init__(self, initial_status: str = "idle") -> None:
        self.status = initial_status
        self._subscribers: set[Subscriber] = set()
        self._lock = threading.Lock()

    def publish(self, status: str) -> None:
        with self._lock:
            if status == self.status:
                return

            self.status = status
            subscribers = tuple(self._subscribers)

        stale_subscribers = []
        for subscriber in subscribers:
            loop, queue = subscriber
            try:
                loop.call_soon_threadsafe(queue.put_nowait, status)
            except RuntimeError:
                stale_subscribers.append(subscriber)

        if stale_subscribers:
            with self._lock:
                self._subscribers.difference_update(stale_subscribers)

    def subscribe(self) -> Subscriber:
        subscriber = (asyncio.get_running_loop(), asyncio.Queue())
        with self._lock:
            self._subscribers.add(subscriber)
            current_status = self.status

        subscriber[1].put_nowait(current_status)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)
