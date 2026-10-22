"""HTTP API for the CLEARWAY UI.

Every input is range-checked (this is a public surface once hosted). Live runs spend
Token Factory and Tavily credits, so they are refused unless CLEARWAY_ALLOW_LIVE is set;
offline runs use the deterministic stub maker and cost nothing.

shortcut: no rate limit / daily budget yet — keep CLEARWAY_ALLOW_LIVE off on any public
host until T14 adds them.
"""
import os
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .auditor import audit
from .catalogue import FixOp
from .planner import Chair
from .rules import DoorSpec
from .orchestrator import run
from .scribe import approved_brief, escalation_brief
from .serialize import run_to_dict

app = FastAPI(title="CLEARWAY")


class ChairIn(BaseModel):
    width_cm: int = Field(70, ge=40, le=100)
    length_cm: int = Field(110, ge=60, le=160)
    caster_climb_mm: int = Field(20, ge=0, le=100)
    name: str = Field("power", max_length=40)


class RunIn(BaseModel):
    door_cm: int = Field(..., ge=40, le=150)
    threshold_mm: int = Field(0, ge=0, le=100)
    chair: ChairIn = Field(default_factory=ChairIn)
    standard: Literal["ADA", "EN17210"] = "ADA"
    live: bool = False


class FixIn(BaseModel):
    fix_id: str = Field(..., max_length=40)
    params: Dict[str, int] = Field(default_factory=dict)


class CardIn(BaseModel):
    kind: Literal["clause", "price"]
    subject: str = Field("", max_length=60)
    title: str = Field("", max_length=200)
    url: str = Field("", max_length=500)
    price_range: Optional[str] = Field(None, max_length=60)
    price_quote: Optional[str] = Field(None, max_length=400)


class BriefIn(BaseModel):
    door_cm: int = Field(..., ge=40, le=150)
    threshold_mm: int = Field(0, ge=0, le=100)
    chair: ChairIn = Field(default_factory=ChairIn)
    standard: Literal["ADA", "EN17210"] = "ADA"
    fix: List[FixIn] = Field(default_factory=list, max_length=5)
    cards: List[CardIn] = Field(default_factory=list, max_length=10)
    live: bool = False


def _live_allowed() -> bool:
    return os.environ.get("CLEARWAY_ALLOW_LIVE", "").lower() in ("1", "true", "yes")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/run")
def run_endpoint(body: RunIn):
    chair = Chair(**body.chair.model_dump())
    door = DoorSpec(clear_width_cm=body.door_cm, threshold_mm=body.threshold_mm)
    if not body.live:
        return run_to_dict(run(door, chair, body.standard), chair)

    if not _live_allowed():
        raise HTTPException(403, "live runs are disabled on this server")
    from .builder import make_llm_maker
    from .llm import LLMError
    from .research import TavilyResearch
    try:
        result = run(door, chair, body.standard, maker=make_llm_maker(), research=TavilyResearch())
    except LLMError as e:
        raise HTTPException(502, f"model call failed: {e}") from None
    return run_to_dict(result, chair)


@app.post("/api/brief")
def brief_endpoint(body: BriefIn):
    """A brief only ever describes a fix that independently passes the Auditor again."""
    chair = Chair(**body.chair.model_dump())
    before = DoorSpec(clear_width_cm=body.door_cm, threshold_mm=body.threshold_mm)
    if body.live and not _live_allowed():
        raise HTTPException(403, "live runs are disabled on this server")
    if not body.fix:
        return escalation_brief(before, chair, body.standard)

    ops = [FixOp(f.fix_id, params=dict(f.params)) for f in body.fix]
    res = audit(before, ops, chair, body.standard)
    if not res.accepted:
        raise HTTPException(409, f"fix does not pass the auditor: {res.reason}")
    from .llm import chat
    return approved_brief(before, res.after, ops, chair, body.standard,
                          [c.model_dump() for c in body.cards], chat=chat if body.live else None)
