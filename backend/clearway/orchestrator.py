"""Orchestrator: runs the agent cast in order and records a per-agent ledger.

Surveyor -> Pilot -> Inspector -> Builder -> Auditor (loop <= max_rounds) -> Human /
Scribe. The Builder here is a deterministic cost-greedy STUB over the catalogue (no
model), so the whole run is free; T8 swaps in the Nemotron Super maker behind the same
interface. Every deciding step is still the deterministic Auditor.
"""
from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional

from .rules import (ACCESS_AISLE_MIN_MM, CLEAR_WIDTH_MIN_MM, ROUTE_WIDTH_MIN_MM, T_SQUARE_MIN_MM,
                    VAN_SPACE_MIN_MM, DoorSpec, RouteSpec, evaluate)
from .catalogue import FixOp
from .twin import twin_for
from .planner import Chair, analyze, drive
from .auditor import audit


@dataclass(frozen=True)
class Event:
    agent: str
    action: str
    ok: bool
    detail: str
    card: Optional[object] = None   # display evidence (clause/price); never reaches the Auditor
    engine: str = ""                # what actually did this step (a model, or deterministic code)


CODE = "deterministic code"
CHECKER = "physics re-drive + rules engine (code)"


def _with_tavily(engine: str, card) -> str:
    return f"{engine} + Tavily" if card is not None else engine


@dataclass(frozen=True)
class RunResult:
    accepted: bool
    escalated: bool
    refused_count: int
    accepted_fix: List[FixOp]
    after: Optional[object]                 # DoorSpec or RouteSpec
    ledger: List[Event] = field(default_factory=list)
    before: Optional[object] = None


def _describe(diff: List[FixOp]) -> str:
    parts = []
    for op in diff:
        p = f"({', '.join(f'{k}={v}' for k, v in op.params.items())})" if op.params else ""
        parts.append(op.fix_id + p)
    return " + ".join(parts) if parts else "no change"


def _candidates(jam, chair: Chair, standard: str) -> List[List[FixOp]]:
    """Cost-greedy order: cheapest plausible fix first (what the stub maker proposes)."""
    if jam.reason == "clear_width":
        code_cm = (CLEAR_WIDTH_MIN_MM[standard] + 9) // 10   # ceil mm -> cm
        target = max(code_cm, chair.width_cm)
        return [[FixOp("offset_hinges")], [FixOp("widen_frame", params={"target_cm": target})]]
    if jam.reason == "threshold":
        return [[FixOp("remove_threshold")]]
    if jam.reason == "turn_radius":
        return [[FixOp("reverse_swing")], [FixOp("remove_wall_segment")]]
    return []


def _up5(mm: int) -> int:
    """Smallest whole-5-cm size that meets a minimum in mm (the twin's grid is 5 cm)."""
    return -(-mm // 50) * 5


def _route_candidates(spec: RouteSpec, jam, chair: Chair) -> List[List[FixOp]]:
    """Cost-greedy for routes: the narrowest change this chair can physically use, then the code size.

    The stub checks feasibility in the simulator, as a contractor would measure; the Auditor
    still re-checks both physics and code independently.
    """
    if spec.kind == "driveway":
        if jam.reason != "ramp":     # no catalogue fix widens a ramp or tightens a van's turn
            return []
        code = _up5(VAN_SPACE_MIN_MM + ACCESS_AISLE_MIN_MM)
        cheapest = spec.width_cm + _up5((jam.required - jam.measured) * 10)   # what the jam measured
        return [[FixOp("widen_bay", params={"target_cm": v})] for v in sorted({min(cheapest, code), code})]
    if spec.kind == "hammerhead" and jam.reason != "clear_width":
        field_name, fix, code = "bar_cm", "extend_turning_bar", _up5(T_SQUARE_MIN_MM)
    else:
        field_name, fix, code = "width_cm", "widen_corridor", _up5(ROUTE_WIDTH_MIN_MM)
    current = getattr(spec, field_name)
    cheapest = next((v for v in range(current + 5, code, 5)
                     if drive(twin_for(replace(spec, **{field_name: v})), chair)), None)
    return [[FixOp(fix, params={"target_cm": v})] for v in (cheapest, code) if v]


def stub_maker(jam, chair: Chair, standard: str, history, spec=None) -> Optional[List[FixOp]]:
    """Deterministic cost-greedy maker: the next untried candidate, or None when out."""
    if isinstance(spec, RouteSpec):
        cands = _route_candidates(spec, jam, chair)
    else:
        cands = _candidates(jam, chair, standard)
    return cands[len(history)] if len(history) < len(cands) else None


def describe_spec(spec) -> str:
    if isinstance(spec, RouteSpec):
        if spec.kind == "driveway":
            return f"driveway bay {spec.width_cm} cm wide; side-entry ramp van"
        if spec.kind == "hammerhead":
            return f"hallway {spec.width_cm} cm wide ending in a T with a {spec.bar_cm} cm bar"
        return f"S-shaped hallway {spec.width_cm} cm wide"
    return f"door {spec.clear_width_cm} cm, step {spec.threshold_mm} mm"


stub_maker.engine = "cost-greedy stub (code)"


def run(before, chair: Chair, standard: str = "ADA",
        context: Optional[dict] = None, max_rounds: int = 2,
        maker: Optional[Callable] = None, research=None) -> RunResult:
    maker = maker or stub_maker
    maker_engine = getattr(maker, "engine", "model")
    ledger: List[Event] = []
    twin = twin_for(before)
    pilot = {"door": "A* planner (code)", "driveway": "van kinematics + ramp (code)"}.get(
        twin.kind, "wheelchair kinematics (code)")
    ledger.append(Event("Surveyor", "load", True,
                        f"{chair.name} chair {chair.width_cm}x{chair.length_cm} cm; {describe_spec(before)}",
                        engine=CODE))

    jam = analyze(twin, chair)
    if jam is None:
        ledger.append(Event("Pilot", "drive", True, "chair reaches the goal; already accessible",
                            engine=pilot))
        return RunResult(True, False, 0, [], before, ledger, before=before)
    ledger.append(Event("Pilot", "drive", False, f"JAM {jam.reason}: {jam.detail}", engine=pilot))

    failed = [f for f in evaluate(before, standard) if not f.passed]
    if failed:
        card = research.clause(failed[0].clause) if research else None
        ledger.append(Event("Inspector", "cite", False, f"{failed[0].clause}: {failed[0].note}", card,
                            engine=_with_tavily("rules engine (code)", card)))

    history = []   # (diff, refusal reason) fed back to the maker
    refused = 0
    for _ in range(max_rounds):
        diff = maker(jam, chair, standard, history, before)
        if diff is None:
            break
        card = research.price(diff[0].fix_id) if research and diff else None
        ledger.append(Event("Builder", "propose", True, _describe(diff), card,
                            engine=_with_tavily(maker_engine, card)))
        res = audit(before, diff, chair, standard, context)
        if res.accepted:
            ledger.append(Event("Auditor", "accept", True,
                                f"both checks pass -> {describe_spec(res.after)}", engine=CHECKER))
            ledger.append(Event("Human", "approve-pending", True, "awaiting user approval", engine="you"))
            return RunResult(True, False, refused, diff, res.after, ledger, before=before)
        refused += 1
        tail = f" [{res.failing_clause}]" if res.failing_clause else ""
        ledger.append(Event("Auditor", "refuse", False, res.reason + tail, engine=CHECKER))
        history.append((diff, res.reason + tail))

    ledger.append(Event("Scribe", "escalate", True,
                        f"no catalogue fix cleared both checks after {refused} "
                        f"attempt(s) -> contractor brief", engine=CODE))
    return RunResult(False, True, refused, [], None, ledger, before=before)


def render(result: RunResult) -> str:
    lines = [f"{'OK ' if e.ok else 'XX '}{e.agent:9} {e.action:16} {e.detail}" for e in result.ledger]
    verdict = ("ACCEPTED" if result.accepted else "ESCALATED") + f" — refused {result.refused_count}"
    return "\n".join(lines + ["-" * 60, verdict])


if __name__ == "__main__":  # quick manual view of the D3 run
    print(render(run(DoorSpec(clear_width_cm=65), Chair(70, 110, name="power"))))
