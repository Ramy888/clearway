import { describe, expect, it } from "vitest";
import { decodedPath, isSpendRoute, parseBody, spendsCredit } from "../src/routes";

// What the Worker uses to decide whether a request spends Token Factory / Tavily credit.
const spends = (method: string, pathname: string, body: unknown) => {
  const path = decodedPath(pathname);
  if (path === null || !isSpendRoute(method, path)) return false;
  const parsed = parseBody(JSON.stringify(body));
  return parsed !== null && spendsCredit(path, parsed);
};

describe("credit-spend detection", () => {
  it("counts a live run, also under percent-encoded spellings", () => {
    expect(spends("POST", "/api/run", { door_cm: 65, live: true })).toBe(true);
    expect(spends("POST", "/api/%72un", { door_cm: 65, live: true })).toBe(true);
    expect(spends("POST", "/%61pi/run", { door_cm: 65, live: true })).toBe(true);
  });

  it("never lets a non-boolean live slip through uncounted", () => {
    // the server rejects these (strict bool), but the Worker must not bet on that
    for (const live of ["yes", 1, "true", "1"]) expect(spends("POST", "/api/run", { live })).toBe(true);
  });

  it("does not count offline runs", () => {
    expect(spends("POST", "/api/run", { door_cm: 65 })).toBe(false);
    expect(spends("POST", "/api/run", { door_cm: 65, live: false })).toBe(false);
  });

  it("counts a live brief only when it has a fix (the only brief that calls a model)", () => {
    expect(spends("POST", "/api/brief", { live: true, fix: [{ fix_id: "widen_frame" }] })).toBe(true);
    expect(spends("POST", "/api/brief", { live: true, fix: [] })).toBe(false);
    expect(spends("POST", "/api/brief", { live: false, fix: [{ fix_id: "widen_frame" }] })).toBe(false);
  });

  it("ignores other methods and paths", () => {
    expect(spends("GET", "/api/run", { live: true })).toBe(false);
    expect(spends("POST", "/api/health", { live: true })).toBe(false);
  });

  it("refuses bodies it cannot read, and malformed escapes", () => {
    expect(parseBody("not json")).toBeNull();
    expect(parseBody("[1,2]")).toBeNull();
    expect(parseBody("null")).toBeNull();
    expect(decodedPath("/api/%E0%A4%A")).toBeNull();
  });
});
