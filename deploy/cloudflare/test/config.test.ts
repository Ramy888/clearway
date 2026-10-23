import { describe, expect, it } from "vitest";
import { modeFor, needsRestart } from "../src/config";

describe("container restarts when its start settings are stale", () => {
  it("is live only with both keys", () => {
    expect(modeFor({ NEBIUS_API_KEY: "n", TAVILY_API_KEY: "t" })).toBe("live");
    expect(modeFor({ NEBIUS_API_KEY: "n" })).toBe("offline");
    expect(modeFor({})).toBe("offline");
  });

  it("restarts a container started before the keys were set", () => {
    expect(needsRestart(true, "offline", "live")).toBe(true);
    expect(needsRestart(true, undefined, "live")).toBe(true); // started before this check existed
  });

  it("leaves a matching or stopped container alone", () => {
    expect(needsRestart(true, "live", "live")).toBe(false);
    expect(needsRestart(false, "offline", "live")).toBe(false); // the next start reads fresh settings
  });
});
