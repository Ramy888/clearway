"""Route presets and real chairs (from published specs), warmed at startup. The UI mirrors these.

A route run plans several times; on the hosted 1/4-vCPU container a cold one takes seconds,
so the presets are computed once in the background when the server starts.
"""
from .orchestrator import run
from .planner import Chair
from .rules import RouteSpec
from .serialize import run_to_dict

# Quantum Q6 Edge 3 Stretto (mid-wheel): 54.6 x 82.6 cm, turning radius 53.3 cm (EASTIN).
Q6 = Chair(55, 83, name="Quantum Q6 Edge 3 Stretto", axle_offset_cm=0, turning_diameter_cm=107)
# Pride R-TRAK (rear-wheel): 61.4 x 88.3 cm, turning radius 65.2 cm (Quantum 2025 sell sheet).
# The axle position is not published; -20 cm is an estimate that keeps the radius achievable.
R_TRAK = Chair(61, 88, name="Pride R-TRAK", axle_offset_cm=-20, turning_diameter_cm=130)

ROUTES = {
    "s_hallway": RouteSpec("s_route", 70, legs=(("E", 300), ("S", 200), ("E", 300))),
    "dead_end": RouteSpec("hammerhead", 95, bar_cm=95),
}


def warm() -> None:
    for spec in ROUTES.values():
        for chair in (Q6, R_TRAK):
            run_to_dict(run(spec, chair), chair)
