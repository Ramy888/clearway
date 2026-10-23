"""JSON payloads for the UI: the twin, the chair's poses, the ledger, the verdict."""
from dataclasses import asdict

from .twin import Twin, twin_for
from .planner import Chair, Plan, plan


def _runs(cells):
    """Compress grid cells into horizontal runs [x, y, width] — a small payload."""
    rows = {}
    for x, y in cells:
        rows.setdefault(y, []).append(x)
    out = []
    for y in sorted(rows):
        xs = sorted(rows[y])
        start = prev = xs[0]
        for x in xs[1:]:
            if x != prev + 1:
                out.append([start, y, prev - start + 1])
                start = x
            prev = x
        out.append([start, y, prev - start + 1])
    return out


def twin_to_dict(t: Twin) -> dict:
    return {
        "W": t.W, "H": t.H, "cell_cm": t.cell_cm, "kind": t.kind, "headings": t.headings,
        "door_cm": t.door_cm, "threshold_mm": t.threshold_mm,
        "width_cm": t.width_cm, "bar_cm": t.bar_cm, "goal_heading": t.goal_heading,
        "walls": _runs(t.blocked), "thresholds": _runs(t.thresholds),
        "start": list(t.start), "goal": list(t.goal), "wall_cols": list(t.wall_cols),
    }


def plan_to_dict(p: Plan) -> dict:
    return {"reached": p.reached, "poses": [list(s) for s in p.poses]}


def _scene(spec, chair: Chair) -> dict:
    t = twin_for(spec)
    scene = {"twin": twin_to_dict(t), "plan": plan_to_dict(plan(t, chair))}
    if t.kind == "driveway":   # the van drives (its poses are the plan); the chair uses the ramp
        from .kinematics import SIENNA, ramp_clear, ramp_strip
        scene["vehicle"] = asdict(SIENNA)
        scene["ramp"] = {"strip": list(ramp_strip(t, chair)), "clear": ramp_clear(t, chair)}
    return scene


def event_to_dict(e) -> dict:
    return {"agent": e.agent, "action": e.action, "ok": e.ok, "detail": e.detail, "engine": e.engine,
            "card": asdict(e.card) if e.card is not None else None}


def run_to_dict(r, chair: Chair) -> dict:
    changed = r.accepted and bool(r.accepted_fix)
    return {
        "chair": asdict(chair),
        "before": _scene(r.before, chair),
        "after": _scene(r.after, chair) if changed else None,
        "ledger": [event_to_dict(e) for e in r.ledger],
        "verdict": {
            "accepted": r.accepted,
            "escalated": r.escalated,
            "refused_count": r.refused_count,
            "accepted_fix": [{"fix_id": op.fix_id, "params": op.params} for op in r.accepted_fix],
            "after_door": asdict(r.after) if r.after else None,
        },
    }
