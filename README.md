# CLEARWAY

**Test-drive your home in a wheelchair before you change it.**

**Live demo:** https://production-clearway.tyzo.nodeops.app · Nebius x NVIDIA Global AI Hackathon, Physical AI track

CLEARWAY is an **accessibility** tool. A family adapting a home for a wheelchair user usually
guesses: they pay for a fix, then find out whether the chair actually fits. CLEARWAY drives a
simulated wheelchair through a digital twin of the home, shows exactly where it jams, and
proposes the cheapest fix that two **independent** checkers cannot refuse: a physics re-drive
of the chair, and a hard-coded accessibility standard (ADA 2010 / EN 17210). You approve what
ships, and you get a contractor brief with cited prices.

The headline result is a refusal: *"Refused 1 of 2 proposed fixes before you saw one."* A model
proposed a fix that let the chair squeeze through but broke the building code, and the Auditor
said no.

## How it works

| Step | Agent | What runs | Can refuse? |
|---|---|---|---|
| 1 | Surveyor | deterministic code: loads the home and the chair | no |
| 2 | Pilot | A* planner (code): drives the chair's real footprint and heading; finds the jam | no |
| 3 | Inspector | rules engine (code) + **Tavily** for the clause text | **yes** |
| 4 | Builder | **Nemotron 3 Super on Nebius Token Factory**: proposes the cheapest catalogue fix, as JSON only; **Tavily** for a cited price | no (maker) |
| 5 | Auditor | physics re-drive + rules engine (code), from raw numbers only | **yes** (checker) |
| 6 | You | approve the fix | — |
| 7 | Scribe | code renders every figure; **Nemotron 3 Ultra** adds a plain-words paragraph | — |

The UI labels every step with what actually ran. Offline runs use a deterministic stub in place
of Super and say so.

**Why it can be trusted (the maker/checker split):**
- The model **proposes**; code **decides**. Accessibility thresholds are constants in
  `rules.py`, never in a prompt or a web result.
- The Builder can only emit ops from a fixed catalogue (widen frame, offset hinges, remove
  threshold, reverse swing, remove a non-load-bearing wall). Its output is untrusted and is
  validated before anything applies it.
- The Auditor never sees the Builder's prose, prices or any twin the Builder touched. It rebuilds
  the home from the raw post-fix numbers, re-drives the chair, and re-checks the code. Both must
  pass.
- The contractor brief is only written for a fix that passes the Auditor again on the server.
  If Ultra's paragraph mentions any number that isn't in the facts, it is withheld.

## Nebius and NVIDIA

- **Nemotron 3 Super** (`nvidia/nemotron-3-super-120b-a12b`) is the Builder: it reads the jam, the
  chair, the catalogue and the Auditor's previous refusal reasons, and proposes the next fix.
  In a live run it proposed widening to 70 cm, was refused on ADA 404.2.3, then proposed 82 cm,
  which passed.
- **Nemotron 3 Ultra** (`nvidia/Nemotron-3-Ultra-550b-a55b`) writes the brief's plain-words paragraph.
- Both are called at runtime through **Nebius Token Factory** (OpenAI-compatible API,
  `backend/clearway/llm.py`). Super and Ultra are served from `us-central1`.
- **Tavily** fetches the cited clause text and contractor price ranges, shown as linked cards.

## Run it

```bash
cd backend
uv sync
uv run python -m unittest discover -s tests    # the core also runs on plain python3
uv run uvicorn clearway.api:app --port 8000

cd ../web
npm install
npm run dev                                    # http://localhost:5173, proxies /api to :8000
```

Offline runs need no keys and cost nothing. Live runs need `NEBIUS_API_KEY` and
`TAVILY_API_KEY` in `.env` (see `.env.example`) and `CLEARWAY_ALLOW_LIVE=1`. They are
rate-limited per client and capped per day before any model call.

**Deploy:** the `Dockerfile` builds the UI and serves it from FastAPI. The live demo runs on
CreateOS; `deploy/cloudflare` is a tested alternative (a Worker in front of a Cloudflare
Container that keeps the daily cap in a Durable Object).

## Limitations

These are known and deliberate for a hackathon build:

- **The twin is 2D and comes from templates.** The three homes are presets with one doorway each;
  there is no floor-plan import or room editor yet.
- **The chair is a rectangle on a 5 cm grid with 4 headings.** It turns 90° in place and moves
  straight; there are no diagonal moves or swept-turn geometry, so tight L-shaped corridors are
  not modelled.
- **The rule pack is small**: door clear width, threshold height and turning diameter (ADA
  404.2.3 / 404.2.5 / 304.3 and EN 17210 equivalents). It is guidance, not a compliance
  certificate.
- **Fix effects are simplified** (for example, offset hinges add 5 cm). Load-bearing walls are
  never removed; that fix needs explicit permission and a professional.
- **Prices are quoted from web pages** found by Tavily and picked by heuristics (relevance to
  doors/walls, a stated range beats a single figure). They can be in another currency or out of
  date, and are always shown with their source link.
- **The brief's number guard checks digit runs.** A digit that also appears in a clause number
  could pass it.
- **The hosted demo's daily live cap is kept in memory**, so it resets when the container
  restarts, and its rate limits are shared by all visitors.
- **The Builder can propose something useless.** The Auditor refuses it, but that uses one of the
  two rounds, after which the run escalates honestly to a contractor brief.

## License

MIT — see [LICENSE](LICENSE).
