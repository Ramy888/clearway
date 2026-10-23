// Hosted CLEARWAY demo on Cloudflare Containers: this Worker, then one container running the
// CLEARWAY server (FastAPI + the built UI). Live runs call Nemotron on Token Factory and Tavily;
// this Worker caps them per UTC day and in total in Durable Object storage, which survives the
// container sleeping (the server's own in-memory count does not).
import { Container, getContainer } from "@cloudflare/containers";
import { type Caps, release, remaining, reserve } from "./budget";
import { type Mode, modeFor, needsRestart } from "./config";
import { decodedPath, isSpendRoute, parseBody, spendsCredit } from "./routes";

interface Env {
  CLEARWAY: DurableObjectNamespace<Clearway>;
  NEBIUS_API_KEY?: string;
  TAVILY_API_KEY?: string;
  LIVE_RUNS_PER_DAY?: string;
  LIVE_RUNS_TOTAL?: string;
}

const caps = (env: Env): Caps => ({
  perDay: Number(env.LIVE_RUNS_PER_DAY ?? 15),
  total: Number(env.LIVE_RUNS_TOTAL ?? 600),
});

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

export class Clearway extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = "15m";
  enableInternet = true; // Token Factory and Tavily

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);
    this.envVars = {
      // live mode only when both keys are configured; otherwise the demo runs offline (free)
      CLEARWAY_ALLOW_LIVE: modeFor(env) === "live" ? "1" : "",
      // the Worker sets X-Forwarded-For to the visitor's address, so per-visitor limits work
      CLEARWAY_TRUST_PROXY: "1",
      CLEARWAY_LIVE_RUNS_PER_DAY: String(caps(env).perDay),
      NEBIUS_API_KEY: env.NEBIUS_API_KEY ?? "",
      TAVILY_API_KEY: env.TAVILY_API_KEY ?? "",
    };
  }

  override async onStart(): Promise<void> {
    await this.ctx.storage.put("startedAs", modeFor(this.env));
  }

  override async fetch(req: Request): Promise<Response> {
    const path = decodedPath(new URL(req.url).pathname);
    if (path === null) return json({ detail: "malformed path" }, 400);
    const store = this.ctx.storage;
    const now = new Date();
    const running = Boolean(this.ctx.container?.running);
    if (needsRestart(running, await store.get<Mode>("startedAs"), modeFor(this.env))) {
      await this.destroy(); // the request below starts it again with the current settings
    }

    if (isSpendRoute(req.method, path)) {
      const body = parseBody(await req.clone().text());
      if (body === null) return json({ detail: "request body must be a JSON object" }, 400);
      if (!spendsCredit(path, body)) return super.fetch(req);
      // Reserve before forwarding and release on failure: the DO serves other requests while it
      // awaits the container, so counting only after success could over-admit.
      if (!(await reserve(store, caps(this.env), now))) {
        return json({ detail: "today's live-run budget is used up; try an offline run" }, 429);
      }
      try {
        const res = await super.fetch(req);
        if (res.status !== 200) await release(store, now);
        return res;
      } catch (error) {
        await release(store, now);
        throw error;
      }
    }

    if (req.method === "GET" && path === "/api/health") {
      const res = await super.fetch(req);
      if (!res.ok) return res;
      const info = (await res.json()) as { live?: boolean; live_runs_left_today?: number; host?: unknown };
      if (info.live) info.live_runs_left_today = await remaining(store, caps(this.env), now);
      // what the Worker sees vs. what the running container started with (no secret values)
      info.host = { configured: modeFor(this.env), started_as: (await store.get<Mode>("startedAs")) ?? null };
      return json(info);
    }

    return super.fetch(req);
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.protocol === "http:" && url.hostname !== "localhost") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    // Replace any client-supplied X-Forwarded-For with the address Cloudflare saw.
    const headers = new Headers(req.headers);
    headers.set("X-Forwarded-For", req.headers.get("CF-Connecting-IP") ?? "unknown");
    return getContainer(env.CLEARWAY, "demo").fetch(new Request(req, { headers }));
  },
};
