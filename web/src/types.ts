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
  kind?: "door" | "s_route" | "hammerhead" | "driveway";
  headings?: number; // 4 for doors (pivot model); 16 for routes (wheelchair kinematics)
  width_cm?: number;
  bar_cm?: number;
  goal_heading?: number | null;
}

export interface Scene {
  twin: Twin;
  plan: { reached: boolean; poses: Pose[] }; // driveway: the van's poses (rear axle)
  vehicle?: Vehicle; // driveway only: the van that drives; the chair uses its ramp
  ramp?: { strip: [number, number, number, number]; clear: boolean }; // cells x, y, w, h
}

export interface Vehicle {
  name: string;
  length_cm: number;
  width_cm: number;
  axle_offset_cm: number; // rear axle relative to the centre (negative = behind)
  min_radius_cm: number;
  ramp_length_cm: number;
  ramp_width_cm: number;
  wheelbase_cm: number;
  caster_climb_mm: number;
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
  engine: string; // what actually did the step: a Nemotron model, Tavily, or deterministic code
  card: Card | null;
}

export interface Verdict {
  accepted: boolean;
  escalated: boolean;
  refused_count: number;
  accepted_fix: { fix_id: string; params: Record<string, number> }[];
  after_door: Record<string, unknown> | null; // the accepted door or route spec
}

export interface ChairSpec {
  width_cm: number;
  length_cm: number;
  caster_climb_mm: number;
  name: string;
  axle_offset_cm?: number; // drive axle relative to the centre: 0 mid-wheel, negative rear-wheel
  turning_diameter_cm?: number; // from the spec sheet; 0 or absent = unknown (square corners)
}

export interface RouteSpec {
  kind: "s_route" | "hammerhead" | "driveway";
  width_cm: number;
  bar_cm?: number;
  legs?: [string, number][];
}

export interface RunPayload {
  chair: ChairSpec;
  before: Scene;
  after: Scene | null;
  ledger: LedgerEvent[];
  verdict: Verdict;
}

export interface RunRequest {
  door_cm?: number;
  threshold_mm?: number;
  route?: RouteSpec;
  chair: ChairSpec;
  standard: "ADA" | "EN17210";
  live: boolean;
}
