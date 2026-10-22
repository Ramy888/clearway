import { useEffect, useState } from "react";
import { chairPose } from "./model";
import type { ChairSpec, Scene } from "./types";

const STEP_MS = 45;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

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

/** Top-down twin with the chair driving its real planned poses. Remount (key) to replay. */
export function TwinView({ scene, chair }: { scene: Scene; chair: ChairSpec }) {
  const { twin, plan } = scene;
  const last = plan.poses.length - 1;
  const [i, setI] = useState(() => (prefersReducedMotion() ? last : 0));

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let k = 0;
    const id = setInterval(() => {
      k += 1;
      setI(k);
      if (k >= last) clearInterval(id);
    }, STEP_MS);
    return () => clearInterval(id);
  }, [last]);

  const done = i >= last;
  const jammed = done && !plan.reached;
  const isDoor = (twin.kind ?? "door") === "door";
  const p = chairPose(plan.poses[Math.min(i, last)], chair, twin);
  const [gx, gy] = twin.goal;
  const doorX = twin.wall_cols[0] ?? 0;
  const wallThick = twin.wall_cols.length || 1;
  const doorCells = Math.floor(twin.door_cm / twin.cell_cm);
  const doorTop = Math.floor(twin.H / 2) - Math.floor(doorCells / 2);
  const status = statusText(scene, chair, done);

  return (
    <figure className="twin">
      {!isDoor && (
        <p className="twin-meta">
          Hallway {twin.width_cm} cm{twin.kind === "hammerhead" ? ` · turning space ${twin.bar_cm} cm` : " · two bends"}
        </p>
      )}
      <svg viewBox={`0 0 ${twin.W} ${twin.H}`} role="img" aria-label={`Floor plan. ${status}`} shapeRendering="crispEdges">
        <rect x={0} y={0} width={twin.W} height={twin.H} className="floor" />
        {twin.walls.map(([x, y, w]) => (
          <rect key={`w${x}-${y}`} x={x} y={y} width={w} height={1} className="wall" />
        ))}
        {twin.thresholds.map(([x, y, w]) => (
          <rect key={`t${x}-${y}`} x={x} y={y} width={w} height={1} className="step" />
        ))}
        <circle cx={gx + 0.5} cy={gy + 0.5} r={3} className="goal" />
        {isDoor ? (
          <>
            <line
              x1={doorX + wallThick / 2}
              y1={doorTop}
              x2={doorX + wallThick / 2}
              y2={doorTop + doorCells}
              className={jammed ? "door-gap bad" : done ? "door-gap good" : "door-gap"}
            />
            <text x={doorX + wallThick + 2} y={doorTop - 2} className="door-label">
              {twin.door_cm} cm
            </text>
          </>
        ) : null}
        <g
          className={jammed ? "chair jammed" : "chair"}
          transform={`translate(${p.cx} ${p.cy}) rotate(${p.deg})`}
          shapeRendering="geometricPrecision"
        >
          <rect x={-p.L / 2} y={-p.W / 2} width={p.L} height={p.W} rx={2} />
          <line x1={p.L / 2} y1={-p.W / 2} x2={p.L / 2} y2={p.W / 2} className="front" />
        </g>
      </svg>
      <figcaption role="status" aria-live="polite" className={jammed ? "status bad" : done ? "status good" : "status"}>
        {status}
      </figcaption>
    </figure>
  );
}
