import { useState, type ChangeEvent } from "react";
import { Ledger } from "./Ledger";
import { TwinView } from "./TwinView";
import { CHAIRS, PRESETS, describeFix, refusalSummary, runScenario } from "./model";
import type { ChairSpec, RunPayload } from "./types";

type Standard = "ADA" | "EN17210";

export default function App() {
  const [presetId, setPresetId] = useState<string>(PRESETS[0].id);
  const [chair, setChair] = useState<ChairSpec>(CHAIRS[0]);
  const [standard, setStandard] = useState<Standard>("ADA");
  const [live, setLive] = useState(false);
  const [data, setData] = useState<RunPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<"before" | "after">("before");
  const [approved, setApproved] = useState(false);
  const [runId, setRunId] = useState(0);

  async function testDrive() {
    const preset = PRESETS.find((p) => p.id === presetId)!;
    setBusy(true);
    setError(null);
    setApproved(false);
    try {
      const payload = await runScenario({
        door_cm: preset.door_cm,
        threshold_mm: preset.threshold_mm,
        chair,
        standard,
        live,
      });
      setData(payload);
      setPhase("before");
      setRunId((n) => n + 1);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const setDim = (key: "width_cm" | "length_cm" | "caster_climb_mm") => (ev: ChangeEvent<HTMLInputElement>) =>
    setChair((c) => ({ ...c, [key]: Number(ev.target.value) }));

  const scene = data ? (phase === "after" && data.after ? data.after : data.before) : null;
  const summary = data ? refusalSummary(data.ledger) : null;
  const fix = data?.verdict.accepted_fix ?? [];

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          CLEARWAY
        </div>
        <p className="tag">Test-drive your home in a wheelchair before you change it.</p>
      </header>

      <main className="grid">
        <section className="panel controls" aria-label="Setup">
          <h2>1 · The home</h2>
          <div className="choices" role="radiogroup" aria-label="Home">
            {PRESETS.map((p) => (
              <label key={p.id} className={presetId === p.id ? "choice on" : "choice"}>
                <input type="radio" name="home" value={p.id} checked={presetId === p.id} onChange={() => setPresetId(p.id)} />
                <span className="choice-title">{p.label}</span>
                <span className="choice-blurb">{p.blurb}</span>
              </label>
            ))}
          </div>

          <h2>2 · The chair</h2>
          <label className="field">
            <span>Type</span>
            <select
              value={chair.name}
              onChange={(e) => setChair(CHAIRS.find((c) => c.name === e.target.value) ?? CHAIRS[0])}
            >
              {CHAIRS.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} chair
                </option>
              ))}
            </select>
          </label>
          <div className="dims">
            <label className="field">
              <span>Width cm</span>
              <input type="number" min={40} max={100} value={chair.width_cm} onChange={setDim("width_cm")} />
            </label>
            <label className="field">
              <span>Length cm</span>
              <input type="number" min={60} max={160} value={chair.length_cm} onChange={setDim("length_cm")} />
            </label>
            <label className="field">
              <span title="Highest step the front casters can roll over">Climb mm</span>
              <input type="number" min={0} max={100} value={chair.caster_climb_mm} onChange={setDim("caster_climb_mm")} />
            </label>
          </div>

          <h2>3 · The code</h2>
          <div className="seg" role="radiogroup" aria-label="Standard">
            {(["ADA", "EN17210"] as Standard[]).map((s) => (
              <label key={s} className={standard === s ? "on" : ""}>
                <input type="radio" name="std" checked={standard === s} onChange={() => setStandard(s)} />
                {s === "ADA" ? "ADA 2010" : "EN 17210"}
              </label>
            ))}
          </div>

          <label className="live">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            Live agents (Nemotron on Nebius + Tavily)
          </label>

          <button className="primary" onClick={testDrive} disabled={busy}>
            {busy ? "Driving…" : "Test-drive this home"}
          </button>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </section>

        <section className="panel stage" aria-label="Digital twin">
          {data && scene ? (
            <>
              <div className="tabs" role="tablist" aria-label="Scene">
                <button role="tab" aria-selected={phase === "before"} onClick={() => setPhase("before")}>
                  Before
                </button>
                <button
                  role="tab"
                  aria-selected={phase === "after"}
                  disabled={!data.after}
                  onClick={() => setPhase("after")}
                >
                  After fix
                </button>
              </div>
              <TwinView key={`${runId}-${phase}`} scene={scene} chair={data.chair} />
            </>
          ) : (
            <div className="empty">
              <p>Pick a home and a chair, then test-drive it.</p>
              <p className="muted">The chair drives the real route. Where it jams, the agents propose fixes, and an independent auditor refuses any fix that fails physics or code.</p>
            </div>
          )}
        </section>

        <aside className="panel side" aria-label="Agents">
          {data && summary ? (
            <>
              <div className={data.verdict.accepted ? "verdict good" : "verdict esc"}>
                <p className="verdict-line">{summary.sentence}</p>
                {fix.length > 0 && data.verdict.after_door && (
                  <p className="muted">
                    Fix: <b>{fix.map(describeFix).join(" + ")}</b>
                  </p>
                )}
                {data.verdict.escalated && (
                  <p className="muted">No catalogue fix cleared both checks. A contractor brief is the honest next step.</p>
                )}
                {fix.length > 0 &&
                  (approved ? (
                    <p className="approved">Approved. The contractor brief comes next.</p>
                  ) : (
                    <button className="primary" onClick={() => setApproved(true)}>
                      Approve this fix
                    </button>
                  ))}
              </div>
              <Ledger events={data.ledger} />
            </>
          ) : (
            <p className="muted">Each agent's step appears here: what it saw, what it proposed, and what the auditor refused.</p>
          )}
        </aside>
      </main>

      <footer className="foot">
        The model proposes. Code decides. An independent auditor that never sees the pitch can veto. You approve.
      </footer>
    </div>
  );
}
