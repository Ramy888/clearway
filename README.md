# CLEARWAY

**Test-drive your home in a wheelchair before you change it.**

**Live demo:** https://production-clearway.tyzo.nodeops.app · Nebius x NVIDIA Global AI Hackathon, Physical AI track

CLEARWAY is an **accessibility** tool. A family adapting a home for a wheelchair user usually
guesses: they pay for a fix, then find out whether the chair actually fits. CLEARWAY drives a
simulated wheelchair through a digital twin of the home (doorways, S-shaped hallways, dead
ends where it must turn around, and the driveway where a ramp van parks), shows exactly where it
jams, and
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
| 2 | Pilot | code: an A* planner through doorways; for hallways, wheelchair kinematics (turns about its drive axle, drives arcs, reverses, every move's sweep checked) | no |
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

## How the hallway physics is checked

Turning is where a naive model lies, so the route planner is calibrated against closed-form
geometry before it judges anything (`backend/tests/test_kinematics.py`): it never passes a
hallway narrower than the chair; it never clears a 90-degree corner below the rigid-body bound
(L/2 + W)/sqrt(2), and a mid-wheel chair clears within 10 cm of it; it respects the bounds for
turning around in a square room; and wider spaces and mirrored layouts never change a verdict
the wrong way.

The route presets use a real chair from its published spec: the **Quantum Q6 Edge 3 Stretto**
(mid-wheel; 54.6 x 82.6 cm, turning radius 53.3 cm, EASTIN database). The **Pride R-TRAK**
(rear-wheel; 61.4 x 88.3 cm, turning radius 65.2 cm, Quantum 2025 sell sheet) is also offered.
The footprint's corners are trimmed until its pivot circle matches the spec-sheet turning
diameter, because real chairs have rounded casters and footplates.

For doorways the chair is usually physically fine below code, so the Auditor refuses on code.
Hallways work the same way with these chairs: the cheapest width the Q6 can use (80 cm) is under
ADA 403.5.1's 915 mm and is refused; for a dead end, the smallest T it can turn in (100 cm) is
under 304.3.2's 1525 mm square and is refused.

## Car mode: a side-entry ramp van at home

The same engine drives a car. A **BraunAbility Toyota Sienna side-entry van** (5174 x 1994 mm,
3061 mm wheelbase, 5.8 m turning radius; BraunAbility's 52 in in-floor ramp) turns from the street
into a driveway bay, parks nose-in, and deploys its ramp; then the chair rolls off it.

- **A car cannot pivot.** It is the same rigid footprint keyed on its rear axle, but it only drives
  straight or along arcs of its minimum turning radius, checked often enough that the sliver missed
  between checked poses stays under half a grid cell. Calibration (`test_car_kinematics.py`): a
  ring track just wider than the closed-form swept annulus [R - W/2, sqrt((R + W/2)^2 + a^2)] is
  driveable and a narrower one jams; the van never pivots; it cannot turn around where a chair can.
- **It drives like a driver.** The planner first tries the direct manoeuvre (straight on, one
  full-lock quarter turn, straight in) with the same moves and checks, as Hybrid A* does; only if
  that does not fit does a guided search look for another way.
- **Two checkers, again.** Physics: the ramp plus the chair's own length must fit beside the parked
  van. Code: ADA 502.2 van space 3350 mm + 502.3.1 access aisle 1525 mm. A 350 cm bay jams the
  ramp; the cheapest bay the Q6 can use (445 cm) is refused under ADA; 490 cm passes both.

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

- **The twin is 2D and comes from templates.** Six presets (three doorways, two hallways, a driveway);
  there is no floor-plan import or room editor yet. Hallways are made of straight legs with
  alternating 90-degree turns; U-turns (governed by ADA 403.5.2) are not modelled, and hallways
  are checked against ADA only.
- **Car mode models one manoeuvre and one van.** Bays narrower than 350 cm would need a
  multi-point turn and are refused at the input; the van parks 30 cm off the driver's wall; the
  ramp door is taken as centred on the van and the chair's turn after the ramp is not modelled.
  Where the Sienna's rear axle sits (110 cm from the rear bumper) is an estimate. ADA 502 governs
  public parking; for a private driveway it is the reference the brief cites.
- **Doorways use a simpler chair model** (a rectangle that pivots in 90-degree steps), which is
  enough for straight passage. Hallways use the kinematic model above.
- **The kinematic chair is a rigid footprint on a 5 cm grid with 16 headings.** It can be up to one
  grid cell more pessimistic than reality, never more optimistic. Without a spec-sheet turning
  diameter its corners stay square, which overstates the space it needs to turn. Spec sheets do
  not publish where the drive axle sits; the R-TRAK's is an estimate.
- **The rule pack is small**: door clear width, threshold height, turning diameter, hallway width and van parking (ADA
  404.2.3 / 404.2.5 / 304.3 / 403.5.1 / 502 and EN 17210 for doors). It is guidance, not a compliance
  certificate.
- **Fix effects are simplified** (for example, offset hinges add 5 cm). Load-bearing walls are
  never removed; that fix needs explicit permission and a professional.
- **Prices are quoted from web pages** found by Tavily and picked by heuristics (relevance to
  doors/walls, a stated range beats a single figure). They can be in another currency or out of
  date, and are always shown with their source link.
- **The brief's number guard checks digit runs.** A digit that also appears in a clause number
  could pass it.
- **The hosted demo's daily live cap is kept in memory**, so it resets when the container
  restarts, and its rate limits are shared by all visitors. Preset hallway runs are computed
  once at startup so they answer quickly on the small container.
- **The Builder can propose something useless.** The Auditor refuses it, but that uses one of the
  two rounds, after which the run escalates honestly to a contractor brief.

## License

MIT — see [LICENSE](LICENSE).
