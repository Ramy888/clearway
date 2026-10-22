"""The standards rule engine: deterministic, versioned, independent of any model.

Accessibility thresholds live here as constants in code. The Builder (an LLM) and
Tavily may supply clause *text* and prices, but never these numbers. The Auditor runs
this engine on the raw measurements so a fix must satisfy the code, not the sales pitch.

shortcut: ADA 404 + EN 17210 width/threshold/turning only; add ramp slope + reach
ranges when the fix catalogue needs them.
"""
from dataclasses import dataclass
from typing import List, Optional

RULE_PACK_VERSION = "ada-404-2010+en17210.v1"

# Code minimums/maximums, in millimetres.
CLEAR_WIDTH_MIN_MM = {"ADA": 815, "EN17210": 850}   # ADA 404.2.3 / EN 17210
THRESHOLD_MAX_MM = 13                                # ADA 404.2.5
TURNING_DIAMETER_MIN_MM = 1500                       # ADA 304.3

_CLAUSE = {
    "ADA": {"clear_width": "ADA 404.2.3", "threshold": "ADA 404.2.5", "turning": "ADA 304.3"},
    "EN17210": {"clear_width": "EN 17210 §12", "threshold": "EN 17210 §12", "turning": "EN 17210 §11"},
}


@dataclass(frozen=True)
class DoorSpec:
    clear_width_cm: int
    threshold_mm: int = 0
    turning_diameter_cm: Optional[int] = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    clause: str
    passed: bool
    measured_mm: int
    required_mm: int      # a minimum for width/turning, a maximum for threshold
    note: str


def evaluate(door: DoorSpec, standard: str = "ADA") -> List[Finding]:
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
        findings.append(Finding(
            "turning", clause["turning"], td_mm >= TURNING_DIAMETER_MIN_MM,
            td_mm, TURNING_DIAMETER_MIN_MM,
            f"turning space {td_mm} mm vs minimum {TURNING_DIAMETER_MIN_MM} mm",
        ))

    return findings


def complies(door: DoorSpec, standard: str = "ADA") -> bool:
    return all(f.passed for f in evaluate(door, standard))
