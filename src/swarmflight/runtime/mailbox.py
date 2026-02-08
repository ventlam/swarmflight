from __future__ import annotations

from collections import defaultdict, deque

from swarmflight.runtime.models import Message


class Mailbox:
    """In-memory mailbox keyed by recipient id."""

    def __init__(self) -> None:
        self._queues: dict[str, deque[Message]] = defaultdict(deque)

    def send(self, message: Message) -> None:
        self._queues[message.recipient].append(message)

    def receive(self, recipient: str) -> Message | None:
        queue = self._queues[recipient]
        if not queue:
            return None
        return queue.popleft()

    def drain(self, recipient: str) -> list[Message]:
        queue = self._queues[recipient]
        messages = list(queue)
        queue.clear()
        return messages

    def pending(self, recipient: str) -> int:
        return len(self._queues[recipient])
