"""Orchestrator: runs the agent cast in order and records a per-agent ledger.

Surveyor -> Pilot -> Inspector -> Builder -> Auditor (loop <= max_rounds) -> Human /
Scribe. The Builder here is a deterministic cost-greedy STUB over the catalogue (no
model), so the whole run is free; T8 swaps in the Nemotron Super maker behind the same
interface. Every deciding step is still the deterministic Auditor.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .rules import DoorSpec, evaluate, CLEAR_WIDTH_MIN_MM
from .catalogue import FixOp
from .twin import two_room_template
from .planner import Chair, analyze
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
    after: Optional[DoorSpec]
    ledger: List[Event] = field(default_factory=list)
    before: Optional[DoorSpec] = None


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


def stub_maker(jam, chair: Chair, standard: str, history) -> Optional[List[FixOp]]:
    """Deterministic cost-greedy maker: the next untried candidate, or None when out."""
    cands = _candidates(jam, chair, standard)
    return cands[len(history)] if len(history) < len(cands) else None


stub_maker.engine = "cost-greedy stub (code)"


def run(before: DoorSpec, chair: Chair, standard: str = "ADA",
        context: Optional[dict] = None, max_rounds: int = 2,
        maker: Optional[Callable] = None, research=None) -> RunResult:
    maker = maker or stub_maker
    maker_engine = getattr(maker, "engine", "model")
    ledger: List[Event] = []
    twin = two_room_template(door_cm=before.clear_width_cm, threshold_mm=before.threshold_mm)
    ledger.append(Event("Surveyor", "load", True,
                        f"{chair.name} chair {chair.width_cm}x{chair.length_cm} cm; "
                        f"door {before.clear_width_cm} cm, step {before.threshold_mm} mm", engine=CODE))

    jam = analyze(twin, chair)
    if jam is None:
        ledger.append(Event("Pilot", "drive", True, "chair reaches the goal; already accessible",
                            engine="A* planner (code)"))
        return RunResult(True, False, 0, [], before, ledger, before=before)
    ledger.append(Event("Pilot", "drive", False, f"JAM {jam.reason}: {jam.detail}", engine="A* planner (code)"))

    failed = [f for f in evaluate(before, standard) if not f.passed]
    if failed:
        card = research.clause(failed[0].clause) if research else None
        ledger.append(Event("Inspector", "cite", False, f"{failed[0].clause}: {failed[0].note}", card,
                            engine=_with_tavily("rules engine (code)", card)))

    history = []   # (diff, refusal reason) fed back to the maker
    refused = 0
    for _ in range(max_rounds):
        diff = maker(jam, chair, standard, history)
        if diff is None:
            break
        card = research.price(diff[0].fix_id) if research and diff else None
        ledger.append(Event("Builder", "propose", True, _describe(diff), card,
                            engine=_with_tavily(maker_engine, card)))
        res = audit(before, diff, chair, standard, context)
        if res.accepted:
            ledger.append(Event("Auditor", "accept", True,
                                f"both checks pass -> {res.after.clear_width_cm} cm, "
                                f"{res.after.threshold_mm} mm step", engine=CHECKER))
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
