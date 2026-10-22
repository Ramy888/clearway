import type { Card, ChairSpec, LedgerEvent, Pose, RouteSpec, RunPayload, RunRequest, Twin } from "./types";

const cells = (cm: number, cellCm: number) => Math.max(1, Math.round(cm / cellCm));

/** The chair's footprint rectangle in cells — the same convention as planner._footprint. */
export function chairBox(pose: Pose, chair: ChairSpec, cellCm: number) {
  const [cx, cy, heading] = pose;
  const wc = cells(chair.width_cm, cellCm);
  const lc = cells(chair.length_cm, cellCm);
  const [w, h] = heading % 2 === 0 ? [lc, wc] : [wc, lc];
  return { x: cx - Math.floor(w / 2), y: cy - Math.floor(h / 2), w, h, heading };
}

/** Where to draw the chair: its centre (cells), heading (degrees), and length/width (cells).
 *
 * Door twins use the 4-heading pivot footprint (chairBox). Route twins use the wheelchair
 * kinematics: the pose is the drive axle, so the centre sits `axle_offset_cm` behind it.
 */
export function chairPose(pose: Pose, chair: ChairSpec, twin: Pick<Twin, "headings" | "cell_cm">) {
  const cell = twin.cell_cm;
  const n = twin.headings ?? 4;
  if (n === 4) {
    const b = chairBox(pose, chair, cell);
    const L = cells(chair.length_cm, cell);
    const W = cells(chair.width_cm, cell);
    return { cx: b.x + b.w / 2, cy: b.y + b.h / 2, deg: pose[2] * 90, L, W };
  }
  const deg = (pose[2] * 360) / n;
  const rad = (deg * Math.PI) / 180;
  const d = (chair.axle_offset_cm ?? 0) / cell; // axle = centre + d * heading
  return { cx: pose[0] - d * Math.cos(rad), cy: pose[1] - d * Math.sin(rad), deg, L: chair.length_cm / cell, W: chair.width_cm / cell };
}

/** "Refused N of M proposed fixes before you saw one." — counted from the ledger. */
export function refusalSummary(ledger: LedgerEvent[]) {
  const proposed = ledger.filter((e) => e.action === "propose").length;
  const refused = ledger.filter((e) => e.action === "refuse").length;
  const sentence =
    refused > 0
      ? `Refused ${refused} of ${proposed} proposed fix${proposed === 1 ? "" : "es"} before you saw one.`
      : proposed > 0
        ? "The first proposed fix passed both checks."
        : "Already accessible: no fix needed.";
  return { proposed, refused, sentence };
}

type FetchFn = (url: string, init: RequestInit) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

async function postJson<T>(url: string, payload: unknown, fetchFn: FetchFn): Promise<T> {
  const res = await fetchFn(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : res.status === 422 ? "invalid input" : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export function runScenario(req: RunRequest, fetchFn: FetchFn = fetch): Promise<RunPayload> {
  return postJson<RunPayload>("/api/run", req, fetchFn);
}

export interface Brief {
  markdown: string;
  narrative_source: "ultra" | "none";
  withheld: boolean;
}

export interface BriefRequest extends RunRequest {
  fix: { fix_id: string; params: Record<string, number> }[];
  cards: Card[];
}

/** The server re-audits `fix` before writing; an empty fix asks for the escalation brief. */
export function fetchBrief(req: BriefRequest, fetchFn: FetchFn = fetch): Promise<Brief> {
  return postJson<Brief>("/api/brief", req, fetchFn);
}

/** Evidence URLs come from web search results: only ever link http(s). */
export function safeHref(url: string): string | null {
  return /^https?:\/\//i.test(url.trim()) ? url.trim() : null;
}

/** Human wording for a catalogue op, e.g. "widen frame to 82 cm". */
export function describeFix(op: { fix_id: string; params: Record<string, number> }): string {
  const target = op.params.target_cm;
  return op.fix_id.replace(/_/g, " ") + (target ? ` to ${target} cm` : "");
}

export interface Preset {
  id: string;
  label: string;
  blurb: string;
  door_cm?: number;
  threshold_mm?: number;
  route?: RouteSpec;
  chair?: string; // the chair the route was calibrated with (mirrors backend presets.py)
}

/** Homes with the defect already in them — nothing is shrunk on camera. */
export const PRESETS: Preset[] = [
  { id: "apartment", label: "1970s apartment", blurb: "Bathroom door, 65 cm clear", door_cm: 65, threshold_mm: 0 },
  { id: "villa", label: "Older villa", blurb: "Wide door with a 40 mm step", door_cm: 90, threshold_mm: 40 },
  { id: "modern", label: "Modern flat", blurb: "Standard 90 cm door, flush floor", door_cm: 90, threshold_mm: 0 },
  {
    id: "s_hallway",
    label: "S-shaped hallway",
    blurb: "Two bends, 70 cm wide",
    route: { kind: "s_route", width_cm: 70, legs: [["E", 300], ["S", 200], ["E", 300]] },
    chair: "Quantum Q6 Edge 3 Stretto",
  },
  {
    id: "dead_end",
    label: "Dead-end hallway",
    blurb: "95 cm wide, no room to turn around",
    route: { kind: "hammerhead", width_cm: 95, bar_cm: 95 },
    chair: "Quantum Q6 Edge 3 Stretto",
  },
];

/** Generic chairs (square corners: worst case) and two real ones from their published specs. */
export const CHAIRS: ChairSpec[] = [
  { name: "power", width_cm: 70, length_cm: 110, caster_climb_mm: 20 },
  { name: "manual", width_cm: 64, length_cm: 100, caster_climb_mm: 15 },
  // EASTIN: 54.6 x 82.6 cm, turning radius 53.3 cm, mid-wheel drive
  { name: "Quantum Q6 Edge 3 Stretto", width_cm: 55, length_cm: 83, caster_climb_mm: 20, axle_offset_cm: 0, turning_diameter_cm: 107 },
  // Quantum 2025 sell sheet: 61.4 x 88.3 cm, turning radius 65.2 cm; axle position estimated
  { name: "Pride R-TRAK", width_cm: 61, length_cm: 88, caster_climb_mm: 20, axle_offset_cm: -20, turning_diameter_cm: 130 },
];
