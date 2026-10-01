"""
Minimal circuit breaker, per model name, in-memory (fine for a single process;
swap the state store for Redis if you run multiple worker processes/pods).

States:
  CLOSED    -> normal, requests go through
  OPEN      -> too many recent failures, skip this model until cooldown expires
  (no HALF_OPEN state for simplicity - after cooldown we just go back to CLOSED
   and let the next real request prove whether it's healthy again)
"""
import time
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class _BreakerState:
    failure_count: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    def __init__(self):
        self._settings = get_settings()
        self._states: dict[str, _BreakerState] = {}

    def is_open(self, model_name: str) -> bool:
        state = self._states.get(model_name)
        if not state or state.failure_count < self._settings.circuit_breaker_failure_threshold:
            return False
        elapsed = time.monotonic() - state.opened_at
        if elapsed >= self._settings.circuit_breaker_cooldown_s:
            # Cooldown expired - reset and allow a fresh attempt.
            self._states[model_name] = _BreakerState()
            return False
        return True

    def record_success(self, model_name: str):
        self._states[model_name] = _BreakerState()

    def record_failure(self, model_name: str):
        state = self._states.setdefault(model_name, _BreakerState())
        state.failure_count += 1
        if state.failure_count == self._settings.circuit_breaker_failure_threshold:
            state.opened_at = time.monotonic()


circuit_breaker = CircuitBreaker()
