"""HTTP API for the CLEARWAY UI.

Every input is range-checked (this is a public surface once hosted). Live runs spend
Token Factory and Tavily credits, so they are refused unless CLEARWAY_ALLOW_LIVE is set,
rate-limited per client, and capped per UTC day (checked before any model call). Offline
runs use the deterministic stub maker and cost nothing, but are still rate-limited.
"""
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .auditor import audit
from .catalogue import FixOp
from .limits import DailyBudget, RateLimiter
from .planner import Chair
from .rules import DoorSpec, RouteSpec
from .twin import validate_route
from .orchestrator import run
from .scribe import approved_brief, escalation_brief
from .serialize import run_to_dict

@asynccontextmanager
async def _lifespan(_app):
    # warm the route presets in the background; requests are served meanwhile
    if os.environ.get("CLEARWAY_WARM", "1") != "0":
        from .presets import warm
        threading.Thread(target=warm, daemon=True).start()
    yield


app = FastAPI(title="CLEARWAY", lifespan=_lifespan)

_WINDOW_S = float(os.environ.get("CLEARWAY_WINDOW_S", "600"))
RUN_LIMIT = RateLimiter(int(os.environ.get("CLEARWAY_RUNS_PER_WINDOW", "30")), _WINDOW_S)
LIVE_LIMIT = RateLimiter(int(os.environ.get("CLEARWAY_LIVE_PER_WINDOW", "3")), _WINDOW_S)
# Every live run spends Token Factory + Tavily credit; this caps what anonymous visitors can spend.
LIVE_BUDGET = DailyBudget(int(os.environ.get("CLEARWAY_LIVE_RUNS_PER_DAY", "40")))
TRUST_PROXY = os.environ.get("CLEARWAY_TRUST_PROXY") == "1"


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if TRUST_PROXY and forwarded:
        # The trusted proxy appends the address it saw; earlier entries are client-supplied.
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _throttle(limiter: RateLimiter, key: str, what: str) -> None:
    wait = limiter.check(key)
    if wait:
        raise HTTPException(429, f"too many {what}; try again in {wait} s", headers={"Retry-After": str(wait)})


def _gate(request: Request, live: bool) -> None:
    """Rate-limit every request; for live ones also require the flag and spend the budget."""
    key = _client_key(request)
    _throttle(RUN_LIMIT, key, "runs")
    if not live:
        return
    if not _live_allowed():
        raise HTTPException(403, "live runs are disabled on this server")
    _throttle(LIVE_LIMIT, key, "live runs")
    if not LIVE_BUDGET.take():
        raise HTTPException(429, "today's live-run budget is used up; try an offline run")


class ChairIn(BaseModel):
    width_cm: int = Field(70, ge=40, le=100)
    length_cm: int = Field(110, ge=60, le=160)
    caster_climb_mm: int = Field(20, ge=0, le=100)
    name: str = Field("power", max_length=40)
    axle_offset_cm: int = Field(0, ge=-60, le=60)         # 0 mid-wheel, negative rear-wheel drive
    turning_diameter_cm: int = Field(0, ge=0, le=300)     # from the spec sheet; 0 = unknown


class RouteIn(BaseModel):
    kind: Literal["s_route", "hammerhead", "driveway"]
    width_cm: int = Field(..., ge=40, le=700)   # per-kind ranges: validate_route
    bar_cm: int = Field(0, ge=0, le=300)
    legs: List[Tuple[str, int]] = Field(default_factory=list, max_length=12)

    def spec(self) -> RouteSpec:
        return RouteSpec(self.kind, self.width_cm, self.bar_cm, tuple(tuple(leg) for leg in self.legs))


class SpecIn(BaseModel):
    """Exactly one of a doorway (door_cm) or a route; routes are checked against ADA only."""
    door_cm: Optional[int] = Field(None, ge=40, le=150)
    threshold_mm: int = Field(0, ge=0, le=100)
    route: Optional[RouteIn] = None
    chair: ChairIn = Field(default_factory=ChairIn)
    standard: Literal["ADA", "EN17210"] = "ADA"
    live: bool = Field(False, strict=True)   # strict: "yes"/1 must not quietly become True

    @model_validator(mode="after")
    def _one_place(self):
        if (self.door_cm is None) == (self.route is None):
            raise ValueError("give exactly one of door_cm or route")
        if self.route is not None:
            if self.standard != "ADA":
                raise ValueError("routes are checked against ADA 2010 only")
            errors = validate_route(self.route.spec())
            if errors:
                raise ValueError("; ".join(errors))
        return self

    def spec(self):
        if self.route is not None:
            return self.route.spec()
        return DoorSpec(clear_width_cm=self.door_cm, threshold_mm=self.threshold_mm)


class RunIn(SpecIn):
    pass


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


class BriefIn(SpecIn):
    fix: List[FixIn] = Field(default_factory=list, max_length=5)
    cards: List[CardIn] = Field(default_factory=list, max_length=10)


def _live_allowed() -> bool:
    return os.environ.get("CLEARWAY_ALLOW_LIVE", "").lower() in ("1", "true", "yes")


@app.get("/api/health")
def health():
    return {"ok": True, "live": _live_allowed(), "live_runs_left_today": LIVE_BUDGET.remaining()}


@app.post("/api/run")
def run_endpoint(body: RunIn, request: Request):
    _gate(request, body.live)
    chair = Chair(**body.chair.model_dump())
    door = body.spec()
    if not body.live:
        return run_to_dict(run(door, chair, body.standard), chair)

    from .builder import make_llm_maker
    from .llm import LLMError
    from .research import TavilyResearch
    try:
        result = run(door, chair, body.standard, maker=make_llm_maker(), research=TavilyResearch())
    except LLMError as e:
        raise HTTPException(502, f"model call failed: {e}") from None
    return run_to_dict(result, chair)


@app.post("/api/brief")
def brief_endpoint(body: BriefIn, request: Request):
    """A brief only ever describes a fix that independently passes the Auditor again."""
    # only a live brief with a fix calls a model, so only that one spends the live budget
    _gate(request, body.live and bool(body.fix))
    chair = Chair(**body.chair.model_dump())
    before = body.spec()
    if not body.fix:
        return escalation_brief(before, chair, body.standard)

    ops = [FixOp(f.fix_id, params=dict(f.params)) for f in body.fix]
    res = audit(before, ops, chair, body.standard)
    if not res.accepted:
        raise HTTPException(409, f"fix does not pass the auditor: {res.reason}")
    from .llm import chat
    return approved_brief(before, res.after, ops, chair, body.standard,
                          [c.model_dump() for c in body.cards], chat=chat if body.live else None)


def mount_web(target: FastAPI, dist: Path) -> None:
    """Serve the built React UI at / (registered last, so /api/* routes win)."""
    if dist.is_dir():
        target.mount("/", StaticFiles(directory=dist, html=True), name="web")


mount_web(app, Path(os.environ.get("CLEARWAY_WEB_DIST", Path(__file__).resolve().parents[2] / "web" / "dist")))
