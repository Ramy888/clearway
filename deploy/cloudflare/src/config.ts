// The container reads its settings (keys, live mode) only when it starts. Secrets set later do not
// reach a running instance, and an instance can run for hours, so the Worker records what each
// start was configured with and restarts the container when that no longer matches.
export type Mode = "live" | "offline";

export const modeFor = (env: { NEBIUS_API_KEY?: string; TAVILY_API_KEY?: string }): Mode =>
  env.NEBIUS_API_KEY && env.TAVILY_API_KEY ? "live" : "offline";

/** Restart when a running container started with other settings, or with none recorded. */
export const needsRestart = (running: boolean, startedAs: Mode | undefined, now: Mode): boolean =>
  running && startedAs !== now;
