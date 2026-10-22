# CLEARWAY

**Test-drive your home before you change it.**

CLEARWAY drives a wheelchair through a digital twin of a home, discovers where it
physically jams against the real accessibility code, and proposes the cheapest fix
that two **independent** checkers cannot refuse — a physics re-drive and a hard-coded
standards engine that never sees the sales pitch. You approve what ships.

The model **proposes**, code **decides**, an independent auditor can **veto**, a human
**approves**. The signature result is *proof-by-refusal*: "Refused N of M proposed
fixes before you saw one."

Built for the Nebius x NVIDIA Global AI Hackathon — Physical AI track.

## How it works

| Agent | Kind | Role |
|---|---|---|
| Surveyor | code + Nemotron Nano | loads the twin, parses the user's situation |
| Pilot | deterministic A* | drives the chair, reports where it jams |
| Inspector | rules engine + Tavily | cites the accessibility clause; can refuse |
| Builder | Nemotron Super | proposes the cheapest catalogue fix (structured diff only) |
| Auditor | deterministic | re-drives + re-checks independently; can refuse |
| Scribe | Nemotron Ultra | writes the contractor brief |

All *deciding* is deterministic code; the models only propose, narrate, and explain.
Accessibility thresholds live in code, not in prompts. Tavily supplies clause text
and local contractor price ranges at runtime.

## Status

Early build. Deterministic core (twin + footprint path planner + rules engine +
auditor) first; agents and UI follow.

## Development

```bash
cd backend
python3 -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
