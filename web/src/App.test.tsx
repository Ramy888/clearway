import { fireEvent, render, screen, within } from "@testing-library/react";
import App from "./App";
import fixture from "./fixtures/run65.json"; // a real /api/run payload from the backend

function reply(ok: boolean, status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok, status, json: async () => body }));
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
  expect(screen.getByText(/approved/i)).toBeTruthy();
});

it("shows the server's reason instead of a blank screen", async () => {
  reply(false, 403, { detail: "live runs are disabled on this server" });
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /test-drive/i }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/live runs are disabled/);
});
