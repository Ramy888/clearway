"""Scribe: the contractor brief. Code renders every figure; the model may only narrate.

The facts section (jam, failed clauses, the audited fix, cited prices with links) is
built from deterministic results. Nemotron Ultra may add a plain-language paragraph,
but if it mentions any number that is not already in the facts, it is withheld.

shortcut: the number guard is set-membership on digit runs, so a digit that happens to
appear in the facts (e.g. a clause number) can pass; tighten if Ultra starts to drift.
"""
import re
from typing import Callable, List, Optional

from . import llm as _llm
from .catalogue import FixOp
from .planner import Chair, analyze
from .rules import DoorSpec, evaluate
from .orchestrator import describe_spec
from .twin import twin_for

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")

SYSTEM = (
    "You are the Scribe agent in CLEARWAY. Write ONE short paragraph, in plain words, telling "
    "a contractor what to change and why, for the household who will read it too. Use ONLY the "
    "facts given. Do not add any number, price, duration, or measurement that is not in the facts. "
    "No lists, no headings."
)


def _numbers(text: str) -> set:
    return {m.group(0).replace(",", "") for m in _NUM.finditer(text)}


def _safe_url(url) -> Optional[str]:
    return url.strip() if isinstance(url, str) and re.match(r"^https?://", url.strip(), re.I) else None


def _fix_text(op: FixOp) -> str:
    target = op.params.get("target_cm")
    return op.fix_id.replace("_", " ") + (f" to {target} cm" if target else "")


def _problem(before: DoorSpec, chair: Chair, standard: str) -> List[str]:
    lines = []
    jam = analyze(twin_for(before), chair)
    if jam:
        lines.append(f"- Physics: {jam.detail}")
    for f in evaluate(before, standard):
        if not f.passed:
            lines.append(f"- {f.clause}: {f.note} ({describe_spec(before)})")
    return lines


def _header(title: str, chair: Chair, standard: str) -> List[str]:
    return [
        f"# {title}", "",
        f"**Chair:** {chair.name}, {chair.width_cm} x {chair.length_cm} cm, casters climb {chair.caster_climb_mm} mm",
        f"**Standard:** {standard}", "",
        "## Measured problem",
    ]


def _facts(before, after, fix, chair, standard, cards) -> str:
    lines = _header("CLEARWAY contractor brief", chair, standard) + _problem(before, chair, standard)
    lines += ["", "## Approved change (re-checked by the independent Auditor)"]
    lines += [f"- {_fix_text(op)}" for op in fix]
    lines.append(f"- Result: {describe_spec(after)}; passes the physics re-drive and {standard} code")
    priced = [c for c in cards if c.get("kind") == "price" and _safe_url(c.get("url"))]
    if priced:
        lines += ["", "## Cited prices (quoted from the source, not estimated)"]
        for c in priced:
            rng = c.get("price_range") or "no price stated"
            lines.append(f"- {str(c.get('subject', '')).replace('_', ' ')}: {rng} ({c.get('title', '')}) "
                         f"<{_safe_url(c.get('url'))}>")
    return "\n".join(lines)


def approved_brief(before: DoorSpec, after: DoorSpec, fix: List[FixOp], chair: Chair, standard: str,
                   cards: List[dict], chat: Optional[Callable] = None) -> dict:
    facts = _facts(before, after, fix, chair, standard, cards)
    narrative, source, withheld = None, "none", False
    if chat is not None:
        try:
            text, _ = chat("ultra", [{"role": "system", "content": SYSTEM},
                                     {"role": "user", "content": facts}], max_tokens=1500)
            text = text.strip()
            if _numbers(text) <= _numbers(facts):
                narrative, source = text, "ultra"
            else:
                withheld = True
        except _llm.LLMError:
            pass  # the code-rendered facts are the brief; the paragraph is optional
    md = facts
    if narrative:
        md += "\n\n## In plain words\n" + narrative
    if withheld:
        md += "\n\n_A model-written summary was withheld because it mentioned a figure not in the facts above._"
    return {"markdown": md, "narrative_source": source, "withheld": withheld}


def escalation_brief(before: DoorSpec, chair: Chair, standard: str) -> dict:
    lines = _header("CLEARWAY contractor brief: assessment needed", chair, standard) + _problem(before, chair, standard)
    lines += [
        "", "## Outcome",
        "- No fix in CLEARWAY's catalogue cleared both independent checks (physics re-drive and code).",
        "- Ask a qualified contractor to assess structural options for this doorway.",
    ]
    return {"markdown": "\n".join(lines), "narrative_source": "none", "withheld": False}
