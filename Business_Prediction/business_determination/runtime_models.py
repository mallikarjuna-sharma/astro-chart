"""Shared method-status and per-run calculation primitives."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, Literal, Optional, TypeVar

T = TypeVar("T")
MethodStatus = Literal["OK", "NO_DATA", "NOT_APPLICABLE", "BLOCKED", "FAILED"]


@dataclass(frozen=True)
class MethodResult(Generic[T]):
    status: MethodStatus
    value: Optional[T] = None
    reason: Optional[str] = None
    degraded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "value": deepcopy(self.value), "reason": self.reason, "degraded": self.degraded}


@dataclass(frozen=True)
class CalculationContext:
    """Per-run fact cache returning isolated copies to every consumer."""
    payload: Any
    _cache: Dict[str, Any] = field(default_factory=dict, init=False, repr=False, compare=False)

    def fact(self, key: str, compute: Callable[[], T]) -> T:
        if key not in self._cache:
            self._cache[key] = deepcopy(compute())
        return deepcopy(self._cache[key])

    def computed_keys(self):
        return tuple(sorted(self._cache))


__all__ = ["MethodResult", "MethodStatus", "CalculationContext"]
