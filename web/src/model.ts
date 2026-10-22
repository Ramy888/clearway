import type { Card, ChairSpec, LedgerEvent, Pose, RunPayload, RunRequest } from "./types";

const cells = (cm: number, cellCm: number) => Math.max(1, Math.round(cm / cellCm));

/** The chair's footprint rectangle in cells — the same convention as planner._footprint. */
export function chairBox(pose: Pose, chair: ChairSpec, cellCm: number) {
  const [cx, cy, heading] = pose;
  const wc = cells(chair.width_cm, cellCm);
  const lc = cells(chair.length_cm, cellCm);
  const [w, h] = heading % 2 === 0 ? [lc, wc] : [wc, lc];
  return { x: cx - Math.floor(w / 2), y: cy - Math.floor(h / 2), w, h, heading };
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

/** Homes with the defect already in them — the door is never shrunk on camera. */
export const PRESETS = [
  { id: "apartment", label: "1970s apartment", blurb: "Bathroom door, 65 cm clear", door_cm: 65, threshold_mm: 0 },
  { id: "villa", label: "Older villa", blurb: "Wide door with a 40 mm step", door_cm: 90, threshold_mm: 40 },
  { id: "modern", label: "Modern flat", blurb: "Standard 90 cm door, flush floor", door_cm: 90, threshold_mm: 0 },
] as const;

export const CHAIRS: ChairSpec[] = [
  { name: "power", width_cm: 70, length_cm: 110, caster_climb_mm: 20 },
  { name: "manual", width_cm: 64, length_cm: 100, caster_climb_mm: 15 },
];
