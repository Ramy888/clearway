import { fireEvent, render, screen, within } from "@testing-library/react";
import App from "./App";
import fixture from "./fixtures/run65.json"; // a real /api/run payload from the backend

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

it("shows the server's reason instead of a blank screen", async () => {
  reply(false, 403, { detail: "live runs are disabled on this server" });
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/live runs are disabled/);
});
