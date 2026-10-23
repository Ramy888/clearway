import { fireEvent, render, screen, within } from "@testing-library/react";
import App from "./App";
import fixture from "./fixtures/run65.json"; // a real /api/run payload from the backend
import routeFixture from "./fixtures/route_s.json"; // a real route payload (S-hallway, Quantum Q6)
import drivewayFixture from "./fixtures/driveway.json"; // a real car-mode payload (350 cm bay, Quantum Q6)

const BRIEF = { markdown: "# CLEARWAY contractor brief\n- widen frame to 82 cm", narrative_source: "none", withheld: false };

/** A fake server: /api/brief returns BRIEF, everything else returns the given /api/run reply. */
function reply(ok: boolean, status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/brief" ? { ok: true, status: 200, json: async () => BRIEF } : { ok, status, json: async () => body },
    ),
  );
}

beforeEach(() => {
  reply(true, 200, fixture);
  // reduced motion: the animation jumps straight to the final pose, so tests are deterministic
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} }) as never;
});

afterEach(() => vi.unstubAllGlobals());

async function runIt() {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  await screen.findByText("Refused 1 of 2 proposed fixes before you saw one.");
}

it("shows the jam, then the refusal before the accepted fix", async () => {
  await runIt();
  expect(screen.getByRole("status").textContent).toMatch(/jam/i);
  const items = within(screen.getByRole("list", { name: /agent ledger/i })).getAllByRole("listitem");
  const actions = items.map((li) => li.dataset.action);
  expect(actions.indexOf("refuse")).toBeLessThan(actions.indexOf("accept"));
  expect(items[actions.indexOf("refuse")].className).toContain("refuse");
});

it("names what did each step, without passing code off as a model", async () => {
  await runIt();
  const items = within(screen.getByRole("list", { name: /agent ledger/i })).getAllByRole("listitem");
  const builder = items.find((li) => li.dataset.action === "propose")!;
  expect(builder.textContent).toContain("cost-greedy stub (code)");
  expect(builder.textContent).not.toContain("Nemotron");
  const auditor = items.find((li) => li.dataset.action === "refuse")!;
  expect(auditor.textContent).toContain("physics re-drive + rules engine (code)");
});

it("plays the fixed home and gates on human approval", async () => {
  await runIt();
  fireEvent.click(screen.getByRole("tab", { name: /after fix/i }));
  expect(screen.getByRole("status").textContent).toMatch(/clears/i);
  fireEvent.click(screen.getByRole("button", { name: /approve/i }));
  const brief = await screen.findByRole("region", { name: /contractor brief/i });
  expect(brief.textContent).toContain("widen frame to 82 cm");
  expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
  // the server gets the audited fix to re-check, not prose
  const call = vi.mocked(fetch).mock.calls.find(([u]) => u === "/api/brief")!;
  const sent = JSON.parse((call[1] as RequestInit).body as string);
  expect(sent.fix).toEqual([{ fix_id: "widen_frame", params: { target_cm: 82 } }]);
  expect(sent.door_cm).toBe(65);
});

it("runs a route preset: sends a route with its real chair and draws the chair rotated", async () => {
  reply(true, 200, routeFixture);
  render(<App />);
  fireEvent.click(screen.getByLabelText(/S-shaped hallway/i));
  expect((screen.getByLabelText(/EN 17210/i) as HTMLInputElement).disabled).toBe(true); // routes: ADA only
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  await screen.findByText("Refused 1 of 2 proposed fixes before you saw one.");
  const call = vi.mocked(fetch).mock.calls.find(([u]) => u === "/api/run")!;
  const sent = JSON.parse((call[1] as RequestInit).body as string);
  expect(sent.route.kind).toBe("s_route");
  expect(sent.door_cm).toBeUndefined();
  expect(sent.chair.name).toBe("Quantum Q6 Edge 3 Stretto");
  expect(screen.getByRole("status").textContent).toMatch(/jam/i);
  expect(document.querySelector("g.chair")!.getAttribute("transform")).toMatch(/rotate\(/);
});

it("car mode: the van drives, its ramp jams before the fix, and the chair rolls off after", async () => {
  reply(true, 200, drivewayFixture);
  render(<App />);
  fireEvent.click(screen.getByLabelText(/Home driveway/i));
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  await screen.findByText("Refused 1 of 2 proposed fixes before you saw one.");
  const call = vi.mocked(fetch).mock.calls.find(([u]) => u === "/api/run")!;
  const sent = JSON.parse((call[1] as RequestInit).body as string);
  expect(sent.route).toEqual({ kind: "driveway", width_cm: 350 });
  expect(sent.chair.name).toBe("Quantum Q6 Edge 3 Stretto");
  expect(screen.getByRole("status").textContent).toBe(
    "JAM at the ramp: ramp and chair need 215 cm beside the van; the bay leaves 121 cm.",
  );
  expect(document.querySelector(".van-glyph")).not.toBeNull();
  expect(document.querySelector(".ramp.bad")).not.toBeNull();
  expect(document.querySelector(".chair-glyph")).toBeNull(); // the chair never got out
  fireEvent.click(screen.getByRole("tab", { name: /after fix/i }));
  expect(screen.getByRole("status").textContent).toMatch(/^Clears: the van parks, the ramp deploys/);
  expect(document.querySelector(".ramp:not(.bad)")).not.toBeNull();
  expect(document.querySelector(".aisle")).not.toBeNull(); // the marked access aisle
  expect(document.querySelector(".chair-glyph")).not.toBeNull();
});

it("shows the server's reason instead of a blank screen", async () => {
  reply(false, 403, { detail: "live runs are disabled on this server" });
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/live runs are disabled/);
});

it("on a phone (one column), brings the twin into view after a test drive; not on wider screens", async () => {
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  await runIt(); // matchMedia mock matches everything: a phone with reduced motion
  expect(scroll).toHaveBeenCalledWith({ behavior: "auto", block: "start" });

  scroll.mockClear();
  window.matchMedia = vi.fn((q: string) => ({ matches: q.includes("reduce"), addEventListener() {}, removeEventListener() {} })) as never;
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  await screen.findByRole("button", { name: /test-drive/i });
  expect(scroll).not.toHaveBeenCalled();
});
