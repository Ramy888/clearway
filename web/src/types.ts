// Mirrors backend/clearway/serialize.py — the /api/run payload.
export type Pose = [number, number, number]; // x, y (cells), heading 0=+x 1=+y 2=-x 3=-y
export type Run = [number, number, number]; // x, y, width (a horizontal run of cells)

export interface Twin {
  W: number;
  H: number;
  cell_cm: number;
  door_cm: number;
  threshold_mm: number;
  walls: Run[];
  thresholds: Run[];
  start: Pose;
  goal: [number, number];
  wall_cols: number[];
}

export interface Scene {
  twin: Twin;
  plan: { reached: boolean; poses: Pose[] };
}

export interface Card {
  kind: "clause" | "price";
  subject: string;
  title: string;
  url: string;
  snippet: string;
  price_range: string | null;
  price_quote: string | null;
}

export interface LedgerEvent {
  agent: string;
  action: string;
  ok: boolean;
  detail: string;
  card: Card | null;
}

export interface Verdict {
  accepted: boolean;
  escalated: boolean;
  refused_count: number;
  accepted_fix: { fix_id: string; params: Record<string, number> }[];
  after_door: { clear_width_cm: number; threshold_mm: number; turning_diameter_cm: number | null } | null;
}

export interface ChairSpec {
  width_cm: number;
  length_cm: number;
  caster_climb_mm: number;
  name: string;
}

export interface RunPayload {
  chair: ChairSpec;
  before: Scene;
  after: Scene | null;
  ledger: LedgerEvent[];
  verdict: Verdict;
}

export interface RunRequest {
  door_cm: number;
  threshold_mm: number;
  chair: ChairSpec;
  standard: "ADA" | "EN17210";
  live: boolean;
}
