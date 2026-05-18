"""Per-bucket circuit breaker for outbound IA API requests.

State machine per bucket:
  CLOSED  → normal operation; failures accumulate
  OPEN    → all calls short-circuit immediately for CIRCUIT_BREAKER_COOLDOWN_S seconds
  (half-open is implicit: after cooldown the next call is let through and either
   resets to CLOSED on success or re-trips to OPEN on failure)

Failure definition: any 5xx HTTP response or network-level RequestError.
Non-failures: 2xx, 3xx, 4xx (including 429 — rate-limited but not degraded).
"""

import time

from wayback_mcp.config import CIRCUIT_BREAKER_COOLDOWN_S, CIRCUIT_BREAKER_THRESHOLD


class CircuitBreaker:
    """Thread-safe (asyncio-safe) per-bucket circuit breaker.

    All methods are synchronous because they only touch in-memory state
    protected by the GIL; no coroutine scheduling is needed.
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        cooldown: float = CIRCUIT_BREAKER_COOLDOWN_S,
    ) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        # Per-bucket state
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def is_open(self, key: str) -> bool:
        """Return True if the circuit for *key* is currently open (tripped)."""
        if key not in self._opened_at:
            return False
        elapsed = time.monotonic() - self._opened_at[key]
        if elapsed >= self._cooldown:
            # Cooldown expired — let the next call through (half-open).
            # Reset failure count so a single success fully closes the breaker.
            del self._opened_at[key]
            self._failures[key] = 0
            return False
        return True

    def record_failure(self, key: str) -> None:
        """Record a 5xx or network error for *key*.

        Trips the breaker when the running failure count reaches the threshold.
        """
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count >= self._threshold:
            self._opened_at[key] = time.monotonic()

    def record_success(self, key: str) -> None:
        """Record a 2xx response for *key*; resets the failure count."""
        self._failures[key] = 0
        self._opened_at.pop(key, None)
