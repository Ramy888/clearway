import { chairBox, chairPose, refusalSummary, runScenario, safeHref } from "./model";

describe("safeHref (card URLs come from web search — untrusted)", () => {
  it("allows http(s)", () => {
    expect(safeHref("https://up.codes/s/doors")).toBe("https://up.codes/s/doors");
    expect(safeHref("http://example.com")).toBe("http://example.com");
  });
  it("drops script and data URLs", () => {
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref(" JavaScript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,<script>")).toBeNull();
    expect(safeHref("")).toBeNull();
  });
});
import type { LedgerEvent, Twin } from "./types";

const power = { width_cm: 70, length_cm: 110, caster_climb_mm: 20, name: "power" };
const ev = (agent: string, action: string): LedgerEvent => ({ agent, action, ok: true, detail: "", engine: "", card: null });

describe("chairBox matches the backend footprint exactly", () => {
  it("facing +x: length runs along x, centred like planner._footprint", () => {
    expect(chairBox([31, 31, 0], power, 5)).toEqual({ x: 20, y: 24, w: 22, h: 14, heading: 0 });
  });
  it("facing +y: width runs along x", () => {
    expect(chairBox([31, 31, 1], power, 5)).toEqual({ x: 24, y: 20, w: 14, h: 22, heading: 1 });
  });
});

describe("chairPose (what the UI draws)", () => {
  it("door twins keep the 4-heading footprint", () => {
    const twin = { headings: 4, cell_cm: 5 } as Twin;
    expect(chairPose([31, 31, 0], power, twin)).toEqual({ cx: 31, cy: 31, deg: 0, L: 22, W: 14 });
    expect(chairPose([31, 31, 1], power, twin)).toEqual({ cx: 31, cy: 31, deg: 90, L: 22, W: 14 });
  });
  it("route twins rotate about the drive axle", () => {
    const twin = { headings: 16, cell_cm: 5 } as Twin;
    const rear = { name: "r", width_cm: 60, length_cm: 100, caster_climb_mm: 20, axle_offset_cm: -20, turning_diameter_cm: 0 };
    const p = chairPose([50, 50, 4], rear, twin); // heading 4 of 16 = 90 degrees (+y)
    expect(p.deg).toBe(90);
    expect(p.cx).toBeCloseTo(50);
    expect(p.cy).toBeCloseTo(54); // axle 20 cm behind the centre: centre is 4 cells ahead
    expect([p.L, p.W]).toEqual([20, 12]);
  });
});

describe("refusalSummary", () => {
  it("counts refusals against proposals", () => {
    const ledger = [ev("Builder", "propose"), ev("Auditor", "refuse"), ev("Builder", "propose"), ev("Auditor", "accept")];
    expect(refusalSummary(ledger)).toEqual({
      proposed: 2,
      refused: 1,
      sentence: "Refused 1 of 2 proposed fixes before you saw one.",
    });
  });
  it("says so when the first fix passed", () => {
    expect(refusalSummary([ev("Builder", "propose"), ev("Auditor", "accept")]).sentence).toBe(
      "The first proposed fix passed both checks.",
    );
  });
  it("says so when no fix was needed", () => {
    expect(refusalSummary([ev("Pilot", "drive")]).sentence).toBe("Already accessible: no fix needed.");
  });
});

describe("runScenario", () => {
  const req = { door_cm: 65, threshold_mm: 0, chair: power, standard: "ADA" as const, live: false };
  const reply = (status: number, body: unknown) =>
    vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

  it("returns the payload on success", async () => {
    const fetchFn = reply(200, { verdict: { accepted: true } });
    await expect(runScenario(req, fetchFn)).resolves.toEqual({ verdict: { accepted: true } });
    expect(fetchFn).toHaveBeenCalledWith("/api/run", expect.objectContaining({ method: "POST" }));
  });
  it("surfaces the server's reason for a refused live run", async () => {
    await expect(runScenario(req, reply(403, { detail: "live runs are disabled on this server" }))).rejects.toThrow(
      "live runs are disabled on this server",
    );
  });
  it("turns validation errors into a plain message", async () => {
    await expect(runScenario(req, reply(422, { detail: [{ msg: "x" }] }))).rejects.toThrow("invalid input");
  });
});
