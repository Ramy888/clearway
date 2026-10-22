"""Builder (maker): Nemotron Super proposes the cheapest catalogue fix as a structured diff.

The model sees the jam, the chair, the constraints, the catalogue, and what the Auditor
already refused (with reasons). It may only answer with catalogue ops in JSON; anything
else parses to nothing. Its output is untrusted: the Auditor validates and re-checks
every op independently, so a bad proposal costs a refusal, never a wrong verdict.
"""
import json
import re
from typing import Callable, List, Optional

from .catalogue import CATALOGUE, FixOp
from . import llm as _llm

SYSTEM = (
    "You are the Builder agent in CLEARWAY, a home-accessibility planner. A wheelchair "
    "jammed on its route. Propose the SINGLE cheapest fix from the catalogue below that "
    "you believe lets this chair through AND meets the building code. You may not invent "
    "fixes, measurements, or parameters outside the listed ranges. An independent "
    "Auditor re-checks everything you propose and refuses fixes that fail.\n"
    'Answer with ONLY a JSON object: {"ops":[{"fix_id":"<id>","params":{...}}]}'
)


def catalogue_text() -> str:
    """The catalogue as the model sees it — derived from CATALOGUE, never hand-listed."""
    lines = []
    for fix_id, d in sorted(CATALOGUE.items(), key=lambda kv: kv[1].rank):
        params = ", ".join(f"{k}: {t.__name__} in [{lo}, {hi}]"
                           for k, (t, lo, hi) in d.params.items()) or "none"
        req = f"; only if {d.requires} is permitted" if d.requires else ""
        lines.append(f"- {fix_id} (relative cost {d.rank}); params: {params}{req}")
    return "\n".join(lines)


def build_messages(jam, chair, standard, history, context=None) -> list:
    jam_text = (f"{jam.reason}: {jam.detail} (measured {jam.measured} {jam.unit}, "
                f"chair needs {jam.required} {jam.unit})") if jam else "route blocked"
    refused = "\n".join(
        f"- {', '.join(op.fix_id + (str(op.params) if op.params else '') for op in diff) or 'empty'}"
        f" -> REFUSED: {reason}"
        for diff, reason in history
    ) or "none yet"
    permitted = ", ".join(k for k, v in (context or {}).items() if v) or "none"
    user = (
        f"Jam: {jam_text}\n"
        f"Chair: {chair.name}, {chair.width_cm} x {chair.length_cm} cm, "
        f"casters climb {chair.caster_climb_mm} mm\n"
        f"Standard: {standard}\n"
        f"Permitted special works: {permitted}\n"
        f"Catalogue:\n{catalogue_text()}\n"
        f"Already refused by the Auditor:\n{refused}"
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse_ops(text: str) -> List[FixOp]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    raw = data.get("ops") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    ops = []
    for o in raw:
        if isinstance(o, dict) and isinstance(o.get("fix_id"), str):
            params = o.get("params")
            ops.append(FixOp(o["fix_id"], params=params if isinstance(params, dict) else {}))
    return ops


def make_llm_maker(chat: Optional[Callable] = None, tier: str = "super",
                   context: Optional[dict] = None) -> Callable:
    """A maker for orchestrator.run backed by a Nemotron tier (chat is injectable)."""
    chat = chat or _llm.chat

    def maker(jam, chair, standard, history):
        content, _ = chat(tier, build_messages(jam, chair, standard, history, context),
                          max_tokens=2048)
        return parse_ops(content)
    maker.engine = f"{_llm.DISPLAY[tier]} · Nebius Token Factory"
    return maker
