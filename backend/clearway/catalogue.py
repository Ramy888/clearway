"""The fixed fix catalogue and the trust boundary around the Builder's output.

The Builder (an LLM) proposes fixes only as a structured diff of catalogue ops. It can
invent nothing: an op is validated for a known id, valid params, and permitted
preconditions before anything applies it. `apply` folds the effects onto a DoorSpec so
the Auditor can re-measure and the rule engine can re-check.

shortcut: effects act on a single DoorSpec measurement; wire them to the full twin when
multi-door routes land.
"""
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Tuple

from .rules import DoorSpec, RouteSpec

_DOOR = ("door",)
_ROUTES = ("s_route", "hammerhead")


def spec_kind(spec) -> str:
    """'door' for a doorway, else the route kind ('s_route' / 'hammerhead')."""
    return spec.kind if isinstance(spec, RouteSpec) else "door"


class InvalidFix(ValueError):
    """Raised when a proposed diff fails the trust boundary."""


@dataclass(frozen=True)
class FixOp:
    fix_id: str
    target_id: str = "door"
    params: dict = field(default_factory=dict)


def _offset_hinges(d, p, c):      return replace(d, clear_width_cm=d.clear_width_cm + 5)
def _widen_frame(d, p, c):        return replace(d, clear_width_cm=p["target_cm"])
def _remove_threshold(d, p, c):   return replace(d, threshold_mm=0)
def _reverse_swing(d, p, c):      return replace(d, turning_diameter_cm=(d.turning_diameter_cm or 120) + 30)
def _remove_wall_segment(d, p, c): return replace(d, turning_diameter_cm=160)
def _widen_corridor(r, p, c):     return replace(r, width_cm=p["target_cm"])
def _extend_turning_bar(r, p, c): return replace(r, bar_cm=p["target_cm"])


@dataclass(frozen=True)
class FixDef:
    effect: Callable
    # param name -> (python type, min, max); empty means no params
    params: Dict[str, tuple] = field(default_factory=dict)
    requires: Optional[str] = None   # a context flag that must be truthy
    cost_key: str = ""               # key for Tavily price lookup later
    rank: int = 0                    # relative cost, 1 = cheapest (until Tavily prices land)
    phrase: str = ""                 # how a contractor would search for this job
    applies_to: Tuple[str, ...] = _DOOR   # which spec kinds this fix can change


CATALOGUE: Dict[str, FixDef] = {
    "remove_threshold":   FixDef(_remove_threshold, cost_key="remove_threshold", rank=1,
                                 phrase="remove a door threshold"),
    "offset_hinges":      FixDef(_offset_hinges, cost_key="offset_hinges", rank=2,
                                 phrase="install offset door hinges"),
    "reverse_swing":      FixDef(_reverse_swing, cost_key="reverse_swing", rank=3,
                                 phrase="reverse a door swing"),
    "widen_frame":        FixDef(_widen_frame, params={"target_cm": (int, 60, 120)}, cost_key="widen_frame",
                                 rank=4, phrase="widen an interior doorway door frame"),
    "remove_wall_segment": FixDef(_remove_wall_segment, requires="allow_wall_removal",
                                  cost_key="remove_wall_segment", rank=5,
                                  phrase="remove a non-load-bearing interior wall"),
    "widen_corridor":     FixDef(_widen_corridor, params={"target_cm": (int, 60, 200)}, cost_key="widen_corridor",
                                 rank=4, phrase="widen a hallway", applies_to=_ROUTES),
    "extend_turning_bar": FixDef(_extend_turning_bar, params={"target_cm": (int, 60, 300)},
                                 cost_key="extend_turning_bar", rank=5,
                                 phrase="enlarge a hallway turning space", applies_to=("hammerhead",)),
}


def validate(diff: List[FixOp], context: Optional[dict] = None, kind: str = "door") -> List[str]:
    """Return a list of errors (empty == valid). Never applies anything."""
    context = context or {}
    errors: List[str] = []
    for i, op in enumerate(diff):
        spec = CATALOGUE.get(op.fix_id)
        if spec is None:
            errors.append(f"[{i}] unknown fix '{op.fix_id}'")
            continue
        if kind not in spec.applies_to:
            errors.append(f"[{i}] {op.fix_id}: does not apply to a {kind.replace('_', ' ')}")
            continue
        for k in op.params:
            if k not in spec.params:
                errors.append(f"[{i}] {op.fix_id}: unexpected param '{k}'")
        for k, (typ, lo, hi) in spec.params.items():
            if k not in op.params:
                errors.append(f"[{i}] {op.fix_id}: missing param '{k}'")
                continue
            v = op.params[k]
            if type(v) is not typ:
                errors.append(f"[{i}] {op.fix_id}: param '{k}' must be {typ.__name__}")
            elif not (lo <= v <= hi):
                errors.append(f"[{i}] {op.fix_id}: {k}={v} out of range [{lo}, {hi}]")
        if spec.requires and not context.get(spec.requires):
            errors.append(f"[{i}] {op.fix_id}: not permitted ({spec.requires} is not set)")
    return errors


def apply(door, diff: List[FixOp], context: Optional[dict] = None):
    """Fold the diff onto a DoorSpec or RouteSpec, after the trust-boundary check."""
    errors = validate(diff, context, spec_kind(door))
    if errors:
        raise InvalidFix("; ".join(errors))
    d = door
    for op in diff:
        d = CATALOGUE[op.fix_id].effect(d, op.params, context or {})
    return d
