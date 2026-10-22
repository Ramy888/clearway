import { useEffect, useState } from "react";
import { chairBox } from "./model";
import type { ChairSpec, Scene } from "./types";

const STEP_MS = 45;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
  const box = chairBox(plan.poses[Math.min(i, last)], chair, twin.cell_cm);
  const [gx, gy] = twin.goal;
  const doorX = twin.wall_cols[0] ?? 0;
  const wallThick = twin.wall_cols.length || 1;
  const doorCells = Math.round(twin.door_cm / twin.cell_cm);
  const doorTop = Math.floor(twin.H / 2) - Math.floor(doorCells / 2);

  // the chair's leading edge, drawn as a bar so its heading is readable
  const front = [
    { x1: box.x + box.w, y1: box.y, x2: box.x + box.w, y2: box.y + box.h },
    { x1: box.x, y1: box.y + box.h, x2: box.x + box.w, y2: box.y + box.h },
    { x1: box.x, y1: box.y, x2: box.x, y2: box.y + box.h },
    { x1: box.x, y1: box.y, x2: box.x + box.w, y2: box.y },
  ][box.heading];

  const status = !done
    ? "Driving the route…"
    : jammed
      ? twin.threshold_mm > chair.caster_climb_mm && twin.door_cm >= chair.width_cm
        ? `JAM at the doorway: a ${twin.threshold_mm} mm step, and the casters climb only ${chair.caster_climb_mm} mm.`
        : `JAM at the doorway: ${twin.door_cm} cm clear, the ${chair.name} chair is ${chair.width_cm} cm wide.`
      : `Clears: the ${chair.name} chair reaches the room through a ${twin.door_cm} cm doorway.`;

  return (
    <figure className="twin">
      <svg
        viewBox={`0 0 ${twin.W} ${twin.H}`}
        role="img"
        aria-label={`Floor plan, door ${twin.door_cm} centimetres. ${status}`}
        shapeRendering="crispEdges"
      >
        <rect x={0} y={0} width={twin.W} height={twin.H} className="floor" />
        {twin.walls.map(([x, y, w]) => (
          <rect key={`w${x}-${y}`} x={x} y={y} width={w} height={1} className="wall" />
        ))}
        {twin.thresholds.map(([x, y, w]) => (
          <rect key={`t${x}-${y}`} x={x} y={y} width={w} height={1} className="step" />
        ))}
        <circle cx={gx + 0.5} cy={gy + 0.5} r={3} className="goal" />
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
        <g className={jammed ? "chair jammed" : "chair"} shapeRendering="geometricPrecision">
          <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={2} />
          <line {...front} className="front" />
        </g>
      </svg>
      <figcaption role="status" aria-live="polite" className={jammed ? "status bad" : done ? "status good" : "status"}>
        {status}
      </figcaption>
    </figure>
  );
}
