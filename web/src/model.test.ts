import { chairBox, refusalSummary, runScenario, safeHref } from "./model";

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
import type { LedgerEvent } from "./types";

const power = { width_cm: 70, length_cm: 110, caster_climb_mm: 20, name: "power" };
const ev = (agent: string, action: string): LedgerEvent => ({ agent, action, ok: true, detail: "", card: null });

describe("chairBox matches the backend footprint exactly", () => {
  it("facing +x: length runs along x, centred like planner._footprint", () => {
    expect(chairBox([31, 31, 0], power, 5)).toEqual({ x: 20, y: 24, w: 22, h: 14, heading: 0 });
  });
  it("facing +y: width runs along x", () => {
    expect(chairBox([31, 31, 1], power, 5)).toEqual({ x: 24, y: 20, w: 14, h: 22, heading: 1 });
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
