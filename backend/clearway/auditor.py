"""Auditor: the independent checker that can refuse a fix.

It receives only the original measurement, the Builder's structured diff, and the chair
— never the Builder's prose, prices, or any twin the Builder may have mutated. It
rebuilds the twin from the raw post-fix numbers and runs two independent gates:

  1. physics re-drive  — does THIS chair actually reach the goal?
  2. code compliance    — does the result meet the standard (numbers from rules.py)?

Both must pass, or the fix is refused with the reason named. This is the maker/checker
separation that stops the system grading its own homework.
"""
from dataclasses import dataclass
from typing import List, Optional

from .rules import DoorSpec, evaluate
from .catalogue import FixOp, apply, validate
from .twin import two_room_template
from .planner import Chair, drive


@dataclass(frozen=True)
class AuditResult:
    accepted: bool
    fix: List[FixOp]
    physics_ok: bool
    code_ok: bool
    before: DoorSpec
    after: Optional[DoorSpec]
    reason: str = ""
    failing_clause: str = ""


def audit(before: DoorSpec, diff: List[FixOp], chair: Chair,
          standard: str = "ADA", context: Optional[dict] = None) -> AuditResult:
    errors = validate(diff, context)
    if errors:
        return AuditResult(False, diff, False, False, before, None,
                           reason="invalid fix: " + "; ".join(errors))

    after = apply(before, diff, context)

    # Independent gate 1: rebuild the twin from raw numbers and re-drive this chair.
    twin = two_room_template(door_cm=after.clear_width_cm, threshold_mm=after.threshold_mm)
    physics_ok = drive(twin, chair)

    # Independent gate 2: code compliance, thresholds straight from rules.py.
    findings = evaluate(after, standard)
    code_ok = all(f.passed for f in findings)

    if physics_ok and code_ok:
        return AuditResult(True, diff, True, True, before, after)

    if not code_ok:
        failed = next(f for f in findings if not f.passed)
        return AuditResult(False, diff, physics_ok, code_ok, before, after,
                           reason=f"code fail: {failed.note}", failing_clause=failed.clause)
    return AuditResult(False, diff, physics_ok, code_ok, before, after,
                       reason="physics fail: chair still cannot reach the goal")
