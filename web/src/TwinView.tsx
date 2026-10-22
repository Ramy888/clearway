import { useEffect, useId, useMemo, useRef, useState, type CSSProperties } from "react";
import { buildTimeline, sampleTimeline, type Timeline } from "./model";
import type { ChairSpec, Run, Scene, Twin } from "./types";

const PLAYBACK = 1.15; // real seconds per timeline second (a touch slower than life, easier to follow)

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const ease = (s: number) => 0.5 - 0.5 * Math.cos(Math.PI * s); // sine in-out: no jolt at start or stop

function statusText(scene: Scene, chair: ChairSpec, done: boolean): string {
  const { twin, plan } = scene;
  const kind = twin.kind ?? "door";
  if (!done) return "Driving the route…";
  if (plan.reached) {
    if (kind === "s_route") return `Clears: the ${chair.name} gets round both bends of a ${twin.width_cm} cm hallway.`;
    if (kind === "hammerhead") return `Clears: the ${chair.name} turns around and drives back out.`;
    return `Clears: the ${chair.name} chair reaches the room through a ${twin.door_cm} cm doorway.`;
  }
  if (kind === "s_route") return `JAM at a bend: the ${chair.name} can't get round a ${twin.width_cm} cm hallway.`;
  if (kind === "hammerhead")
    return `JAM: the ${chair.name} can't turn around here (hallway ${twin.width_cm} cm, turning space ${twin.bar_cm} cm).`;
  if (twin.threshold_mm > chair.caster_climb_mm && twin.door_cm >= chair.width_cm)
    return `JAM at the doorway: a ${twin.threshold_mm} mm step, and the casters climb only ${chair.caster_climb_mm} mm.`;
  return `JAM at the doorway: ${twin.door_cm} cm clear, the ${chair.name} chair is ${chair.width_cm} cm wide.`;
}

const cellsOf = (runs: Run[]) => {
  const s = new Set<string>();
  for (const [x, y, w] of runs) for (let i = 0; i < w; i++) s.add(`${x + i},${y}`);
  return s;
};

/** The open stretch through (x, y) along one axis: [from, to) in cells. */
function openSpan(blocked: Set<string>, twin: Twin, x: number, y: number, vertical: boolean): [number, number] {
  const free = (a: number) => !blocked.has(vertical ? `${x},${a}` : `${a},${y}`);
  const max = vertical ? twin.H : twin.W;
  let a = vertical ? y : x;
  let b = a;
  while (a > 0 && free(a - 1)) a--;
  while (b < max - 1 && free(b + 1)) b++;
  return [a, b + 1];
}

/** Row runs of the given cells (a compact way to draw many unit squares). */
function toRuns(cells: Iterable<string>): Run[] {
  const rows = new Map<number, number[]>();
  for (const c of cells) {
    const [x, y] = c.split(",").map(Number);
    (rows.get(y) ?? rows.set(y, []).get(y)!).push(x);
  }
  const out: Run[] = [];
  for (const [y, xs] of rows) {
    xs.sort((a, b) => a - b);
    let start = xs[0], prev = xs[0];
    for (const x of xs.slice(1)) {
      if (x !== prev + 1) { out.push([start, y, prev - start + 1]); start = x; }
      prev = x;
    }
    out.push([start, y, prev - start + 1]);
  }
  return out;
}

/** Floor = open cells; walls = blocked cells within 2 of the floor; the rest is outside the plan. */
function layers(twin: Twin, blocked: Set<string>) {
  const open: string[] = [], wall: string[] = [];
  for (let y = 0; y < twin.H; y++)
    for (let x = 0; x < twin.W; x++) {
      const k = `${x},${y}`;
      if (!blocked.has(k)) { open.push(k); continue; }
      let near = false;
      for (let dy = -2; dy <= 2 && !near; dy++)
        for (let dx = -2; dx <= 2 && !near; dx++) {
          const nx = x + dx, ny = y + dy;
          near = nx >= 0 && ny >= 0 && nx < twin.W && ny < twin.H && !blocked.has(`${nx},${ny}`);
        }
      if (near) wall.push(k);
    }
  return { floor: toRuns(open), walls: toRuns(wall) };
}

interface Dim { x1: number; y1: number; x2: number; y2: number; label: string; below?: boolean }

/** Floor-plan dimension lines: the door's clear width, or the hallway (and T) widths. */
function dimensions(twin: Twin, blocked: Set<string>): Dim[] {
  const kind = twin.kind ?? "door";
  if (kind === "door") {
    // on the far side of the wall, labelled under the opening: the chair arrives from the left
    const x = (twin.wall_cols[0] ?? 0) + (twin.wall_cols.length || 1) + 1.4;
    const cells = Math.floor(twin.door_cm / twin.cell_cm);
    const top = Math.floor(twin.H / 2) - Math.floor(cells / 2);
    return [{ x1: x, y1: top, x2: x, y2: top + cells, label: `${twin.door_cm} cm`, below: true }];
  }
  const [sx, sy, sh] = twin.start;
  const n = twin.headings ?? 16;
  const alongX = sh % (n / 2) === 0; // the first leg runs along x, so its width is measured along y
  const dims: Dim[] = [];
  if (alongX) {
    const [a, b] = openSpan(blocked, twin, sx, sy, true);
    dims.push({ x1: sx, y1: a, x2: sx, y2: b, label: `${twin.width_cm} cm` });
  } else {
    const y = sy + 12; // below the start, which is also the goal of a turnaround
    const [a, b] = openSpan(blocked, twin, sx, y, false);
    dims.push({ x1: a, y1: y, x2: b, y2: y, label: `${twin.width_cm} cm` });
  }
  if (kind === "hammerhead") {
    let top = 0;
    while (top < twin.H && blocked.has(`${sx},${top}`)) top++;
    const row = top + 2;
    const [a, b] = openSpan(blocked, twin, sx, row, false);
    dims.push({ x1: a, y1: row, x2: b, y2: row, label: `T ${twin.bar_cm} cm`, below: true });
  }
  return dims;
}

/** A wheelchair seen from above, in its own frame (length along +x, centred at 0, units = cells). */
function ChairGlyph({ L, W, d, jammed }: { L: number; W: number; d: number; jammed: boolean }) {
  const tw = Math.max(0.9, 0.13 * W); // tyre thickness
  const midWheel = Math.abs(d) < 0.15 * L;
  const r = (midWheel ? 0.15 : 0.18) * L; // drive wheel radius
  const caster = Math.max(0.6, 0.045 * L);
  return (
    <g className={jammed ? "chair-glyph jammed" : "chair-glyph"}>
      <rect className="chair-shadow" x={-L / 2 + 0.5} y={-W / 2 + 0.8} width={L} height={W} rx={2.4} />
      <rect className="chair-frame" x={-L / 2} y={-W / 2 + tw * 0.6} width={L} height={W - tw * 1.2} rx={1.8} />
      <rect className="chair-seat" x={-0.32 * L} y={-0.3 * W} width={0.5 * L} height={0.6 * W} rx={1.4} />
      <rect className="chair-back" x={-L / 2 + 0.03 * L} y={-0.36 * W} width={0.1 * L} height={0.72 * W} rx={0.8} />
      <rect className="chair-foot" x={0.33 * L} y={-0.22 * W} width={0.13 * L} height={0.44 * W} rx={0.6} />
      {[-1, 1].map((s) => (
        <rect key={`w${s}`} className="chair-wheel" x={d - r} y={s < 0 ? -W / 2 : W / 2 - tw} width={2 * r} height={tw} rx={tw / 2} />
      ))}
      {[-1, 1].map((s) => (
        <circle key={`f${s}`} className="chair-caster" cx={0.42 * L} cy={s * 0.33 * W} r={caster} />
      ))}
      {midWheel &&
        [-1, 1].map((s) => <circle key={`b${s}`} className="chair-caster" cx={-0.42 * L} cy={s * 0.33 * W} r={caster} />)}
      <path className="chair-dir" d={`M ${0.18 * L} ${-0.12 * W} L ${0.27 * L} 0 L ${0.18 * L} ${0.12 * W}`} />
    </g>
  );
}

function useTimeline(tl: Timeline) {
  const reduced = prefersReducedMotion();
  const [t, setT] = useState(() => (reduced ? tl.total : 0));
  useEffect(() => {
    if (reduced || tl.total === 0) {
      setT(tl.total);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const real = tl.total * PLAYBACK * 1000;
    const tick = (now: number) => {
      const s = Math.min(1, (now - t0) / real);
      setT(tl.total * ease(s));
      if (s < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [tl, reduced]);
  return t;
}

/** Plan units per screen pixel, so labels can keep a readable size when a phone shrinks the plan. */
function useUnitsPerPx(units: number) {
  const ref = useRef<SVGSVGElement>(null);
  const [upp, setUpp] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => e.contentRect.width && setUpp(units / e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [units]);
  return [ref, upp] as const;
}

/** Top-down twin with the chair gliding along its real planned path. Remount (key) to replay. */
export function TwinView({ scene, chair, compareTo }: { scene: Scene; chair: ChairSpec; compareTo?: Twin }) {
  const { twin, plan } = scene;
  const uid = useId().replace(/:/g, "");
  const tl = useMemo(() => buildTimeline(plan.poses, chair, twin), [plan.poses, chair, twin]);
  const t = useTimeline(tl);
  const done = t >= tl.total;
  const jammed = done && !plan.reached;
  const isDoor = (twin.kind ?? "door") === "door";
  const p = sampleTimeline(tl, t);
  const blocked = useMemo(() => cellsOf(twin.walls), [twin.walls]);
  const plan2d = useMemo(() => layers(twin, blocked), [twin, blocked]);
  const dims = useMemo(() => dimensions(twin, blocked), [twin, blocked]);
  const trail = tl.keys.filter((k) => k.t <= t).map((k) => sampleTimeline(tl, k.t));
  trail.push(p);
  // after a door fix: cells that were wall before and are open now (what gets built)
  const opened = useMemo(() => {
    if (!compareTo || !isDoor || compareTo.W !== twin.W || compareTo.H !== twin.H) return [];
    const before = cellsOf(compareTo.walls);
    return [...before].filter((c) => !blocked.has(c)).map((c) => c.split(",").map(Number));
  }, [compareTo, isDoor, twin.W, twin.H, blocked]);
  const [gx, gy] = twin.goal;
  const doorX = twin.wall_cols[0] ?? 0;
  const wallThick = twin.wall_cols.length || 1;
  const doorCells = Math.floor(twin.door_cm / twin.cell_cm);
  const doorTop = Math.floor(twin.H / 2) - Math.floor(doorCells / 2);
  const hinge = doorX + wallThick;
  const r = (p.deg * Math.PI) / 180;
  const front = { x: p.cx + (p.L / 2) * Math.cos(r), y: p.cy + (p.L / 2) * Math.sin(r) };
  const dimClass = jammed ? "dim bad" : done && plan.reached ? "dim good" : "dim";
  const status = statusText(scene, chair, done);
  const [svgRef, upp] = useUnitsPerPx(twin.W);
  // label sizes in plan units: the desktop sizes, but never under 10 px (rooms 9 px) on screen
  const dimFs = Math.max(3, 10 * upp);
  const fonts = { "--dim-fs": `${dimFs}px`, "--room-fs": `${Math.max(2.6, 9 * upp)}px` } as CSSProperties;

  return (
    <figure className="twin">
      {!isDoor && (
        <p className="twin-meta">
          Hallway {twin.width_cm} cm{twin.kind === "hammerhead" ? ` · turning space ${twin.bar_cm} cm` : " · two bends"}
        </p>
      )}
      <svg ref={svgRef} style={fonts} viewBox={`0 0 ${twin.W} ${twin.H}`} role="img" aria-label={`Floor plan. ${status}`}>
        <defs>
          <pattern id={`planks${uid}`} width="24" height="6" patternUnits="userSpaceOnUse">
            <rect width="24" height="6" className="plank" />
            <path d="M0 3 H24 M0 6 H24 M8 0 V3 M20 3 V6" className="plank-seam" />
          </pattern>
          <pattern id={`hatch${uid}`} width="1.4" height="1.4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="1.4" height="1.4" className="step" />
            <line x1="0" y1="0" x2="0" y2="1.4" className="step-hatch" />
          </pattern>
          <pattern id={`outside${uid}`} width="2" height="2" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="2" height="2" className="outside" />
            <line x1="0" y1="0" x2="0" y2="2" className="outside-hatch" />
          </pattern>
          <filter id={`depth${uid}`} x="-5%" y="-5%" width="110%" height="110%">
            <feDropShadow dx="0.35" dy="0.55" stdDeviation="0.45" floodOpacity="0.35" />
          </filter>
          <marker id={`arrow${uid}`} viewBox="0 0 6 6" refX="3" refY="3" markerWidth="2.4" markerHeight="2.4" orient="auto-start-reverse">
            <path d="M0 0 L6 3 L0 6 z" className="dim-head" />
          </marker>
        </defs>

        <rect x={0} y={0} width={twin.W} height={twin.H} fill={`url(#outside${uid})`} />
        {plan2d.floor.map(([x, y, w]) => (
          <rect key={`f${x}-${y}`} x={x} y={y} width={w} height={1.02} fill={`url(#planks${uid})`} />
        ))}
        {opened.map(([x, y]) => (
          <rect key={`o${x}-${y}`} x={x} y={y} width={1} height={1} className="opened" />
        ))}
        <g filter={`url(#depth${uid})`} shapeRendering="crispEdges">
          {plan2d.walls.map(([x, y, w]) => (
            <rect key={`w${x}-${y}`} x={x} y={y} width={w} height={1} className="wall" />
          ))}
        </g>
        {twin.thresholds.map(([x, y, w]) => (
          <rect key={`t${x}-${y}`} x={x} y={y} width={w} height={1} fill={`url(#hatch${uid})`} />
        ))}

        {isDoor && (
          <g className="door-symbol">
            <line x1={hinge} y1={doorTop} x2={hinge + doorCells} y2={doorTop} className="door-leaf" />
            <path d={`M ${hinge} ${doorTop + doorCells} A ${doorCells} ${doorCells} 0 0 0 ${hinge + doorCells} ${doorTop}`} className="door-swing" />
            <text x={4} y={5} className="room-label">Hall</text>
            <text x={twin.W - 4} y={5} className="room-label" textAnchor="end">Bathroom</text>
          </g>
        )}

        {trail.length > 1 && <polyline points={trail.map((q) => `${q.cx},${q.cy}`).join(" ")} className="trail" />}

        <g className="goal" transform={`translate(${gx + 0.5} ${gy + 0.5})`}>
          <circle r={3.2} className="goal-ring" />
          <circle r={0.9} className="goal-dot" />
        </g>

        <g className={jammed ? "chair jammed" : "chair"} transform={`translate(${p.cx} ${p.cy}) rotate(${p.deg})`}>
          <ChairGlyph L={p.L} W={p.W} d={tl.d} jammed={jammed} />
        </g>
        {jammed && (
          <g transform={`translate(${front.x} ${front.y})`}>
            <circle r={2.2} className="impact" />
            <circle r={2.2} className="impact delay" />
          </g>
        )}

        {dims.map((m, k) => {
          const vertical = m.x1 === m.x2;
          return (
            <g key={`d${k}`} className={dimClass}>
              <line x1={m.x1} y1={m.y1} x2={m.x2} y2={m.y2} markerStart={`url(#arrow${uid})`} markerEnd={`url(#arrow${uid})`} />
              <text
                x={vertical && !m.below ? m.x1 - 1.2 : vertical ? m.x1 - 0.4 : (m.x1 + m.x2) / 2}
                y={m.below ? m.y2 + 0.4 + dimFs : vertical ? (m.y1 + m.y2) / 2 : m.y1 - 1.2}
                textAnchor={vertical && m.below ? "start" : vertical ? "end" : "middle"}
                dominantBaseline={vertical && !m.below ? "middle" : "auto"}
              >
                {m.label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption role="status" aria-live="polite" className={jammed ? "status bad" : done ? "status good" : "status"}>
        {status}
      </figcaption>
    </figure>
  );
}
