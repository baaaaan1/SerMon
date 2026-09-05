"""Reconnection policy helpers.

A :class:`ReconnectPolicy` only decides *when* to retry; the actual work of
re-establishing a connection is delegated to a caller-supplied callback.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

#: A callable that attempts to reconnect; raises on failure.
ReconnectAction = Callable[[], None]


class ReconnectPolicy:
    """Exponential-backoff reconnection policy.

    Parameters
    ----------
    min_delay:
        Initial backoff in seconds.
    max_delay:
        Upper bound for the backoff in seconds.
    factor:
        Multiplier applied to the delay after each attempt.
    max_attempts:
        Total attempts before giving up (``None`` = unlimited).
    """

    def __init__(
        self,
        *,
        min_delay: float = 1.0,
        max_delay: float = 30.0,
        factor: float = 2.0,
        max_attempts: int | None = None,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.factor = factor
        self.max_attempts = max_attempts
        self._attempt = 0

    @property
    def attempt(self) -> int:
        """Number of attempts made since the last reset."""
        return self._attempt

    def reset(self) -> None:
        """Reset the attempt counter (call after a successful reconnect)."""
        self._attempt = 0

    def next_delay(self) -> float:
        """Return the next backoff, or ``-1`` when attempts are exhausted."""
        if self.max_attempts is not None and self._attempt >= self.max_attempts:
            logger.info("Reconnect attempts exhausted (%d)", self._attempt)
            return -1
        self._attempt += 1
        delay = min(self.max_delay, self.min_delay * (self.factor ** (self._attempt - 1)))
        logger.debug("Reconnect attempt %d in %.2fs", self._attempt, delay)
        return delay

    def run(self, action: ReconnectAction) -> bool:
        """Run *action* until it succeeds or attempts are exhausted.

        Returns ``True`` on success, ``False`` when giving up.
        """
        while True:
            delay = self.next_delay()
            if delay < 0:
                return False
            time.sleep(delay)
            logger.info("Attempting reconnect (attempt %d)", self._attempt)
            try:
                action()
            except Exception as exc:  # noqa: BLE001 -- any failure is a retryable attempt
                logger.warning("Reconnect attempt %d failed: %s", self._attempt, exc)
                continue
            self.reset()
            return True
