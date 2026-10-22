"""The standards rule engine: deterministic, versioned, independent of any model.

Accessibility thresholds live here as constants in code. The Builder (an LLM) and
Tavily may supply clause *text* and prices, but never these numbers. The Auditor runs
this engine on the raw measurements so a fix must satisfy the code, not the sales pitch.

shortcut: ADA 404 + EN 17210 width/threshold/turning only; add ramp slope + reach
ranges when the fix catalogue needs them.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

RULE_PACK_VERSION = "ada-2010+en17210.v2"

# Code minimums/maximums, in millimetres. ADA values checked against access-board.gov (2026-10-22).
CLEAR_WIDTH_MIN_MM = {"ADA": 815, "EN17210": 850}   # ADA 404.2.3 / EN 17210
THRESHOLD_MAX_MM = 13                                # ADA 404.2.5
# ADA 304.3.1: 60 in (1525 mm) circle, checked against access-board.gov (2026-10-22).
# EN 17210's 1500 mm is not re-verified against the standard's text.
TURNING_DIAMETER_MIN_MM = {"ADA": 1525, "EN17210": 1500}
ROUTE_WIDTH_MIN_MM = 915      # ADA 403.5.1 walking surface; also the T's arms and base (304.3.2)
T_SQUARE_MIN_MM = 1525        # ADA 304.3.2: the T-shaped space fits within a 60 in (1525 mm) square

_CLAUSE = {
    "ADA": {"clear_width": "ADA 404.2.3", "threshold": "ADA 404.2.5", "turning": "ADA 304.3.1"},
    "EN17210": {"clear_width": "EN 17210 §12", "threshold": "EN 17210 §12", "turning": "EN 17210 §11"},
}


@dataclass(frozen=True)
class DoorSpec:
    clear_width_cm: int
    threshold_mm: int = 0
    turning_diameter_cm: Optional[int] = None


@dataclass(frozen=True)
class RouteSpec:
    """A route the chair must travel: an S-shaped hallway, or a dead end with a T (hammerhead)."""
    kind: str                                  # "s_route" | "hammerhead"
    width_cm: int                              # clear width of the hallway (and of the T's arms and base)
    bar_cm: int = 0                            # hammerhead: length of the T's bar
    legs: Tuple[Tuple[str, int], ...] = ()     # s_route: orthogonal legs, e.g. (("E", 300), ("S", 200))


@dataclass(frozen=True)
class Finding:
    rule_id: str
    clause: str
    passed: bool
    measured_mm: int
    required_mm: int      # a minimum for width/turning, a maximum for threshold
    note: str


def _evaluate_route(route: RouteSpec) -> List[Finding]:
    w_mm = route.width_cm * 10
    clause = "ADA 304.3.2" if route.kind == "hammerhead" else "ADA 403.5.1"
    findings = [Finding("clear_width", clause, w_mm >= ROUTE_WIDTH_MIN_MM, w_mm, ROUTE_WIDTH_MIN_MM,
                        f"clear width {w_mm} mm vs minimum {ROUTE_WIDTH_MIN_MM} mm")]
    if route.kind == "hammerhead":
        b_mm = route.bar_cm * 10
        findings.append(Finding("turning", "ADA 304.3.2", b_mm >= T_SQUARE_MIN_MM, b_mm, T_SQUARE_MIN_MM,
                                f"T-shaped turning space {b_mm} mm across vs {T_SQUARE_MIN_MM} mm square minimum"))
    return findings


def evaluate(door, standard: str = "ADA") -> List[Finding]:
    if isinstance(door, RouteSpec):
        if standard != "ADA":
            raise ValueError("routes are checked against ADA 2010 only")
        return _evaluate_route(door)
    if standard not in CLEAR_WIDTH_MIN_MM:
        raise ValueError(f"unknown standard: {standard}")
    clause = _CLAUSE[standard]
    findings: List[Finding] = []

    cw_mm = door.clear_width_cm * 10
    cw_req = CLEAR_WIDTH_MIN_MM[standard]
    findings.append(Finding(
        "clear_width", clause["clear_width"], cw_mm >= cw_req, cw_mm, cw_req,
        f"clear width {cw_mm} mm vs minimum {cw_req} mm",
    ))

    findings.append(Finding(
        "threshold", clause["threshold"], door.threshold_mm <= THRESHOLD_MAX_MM,
        door.threshold_mm, THRESHOLD_MAX_MM,
        f"threshold {door.threshold_mm} mm vs maximum {THRESHOLD_MAX_MM} mm",
    ))

    if door.turning_diameter_cm is not None:
        td_mm = door.turning_diameter_cm * 10
        td_req = TURNING_DIAMETER_MIN_MM[standard]
        findings.append(Finding(
            "turning", clause["turning"], td_mm >= td_req, td_mm, td_req,
            f"turning space {td_mm} mm vs minimum {td_req} mm",
        ))

    return findings


def complies(door, standard: str = "ADA") -> bool:
    return all(f.passed for f in evaluate(door, standard))
