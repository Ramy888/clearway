# CLEARWAY demo on Cloudflare Containers

A Worker in front of one container running the CLEARWAY server (FastAPI + the built UI).
Offline runs need no keys and cost nothing. Live runs call Nemotron on Token Factory and Tavily.

What the Worker adds:
- **Credit caps that survive restarts.** Live runs and live briefs are capped per UTC day
  (`LIVE_RUNS_PER_DAY`, 15) and in total (`LIVE_RUNS_TOTAL`, 600) in Durable Object storage. The
  server's own daily count is in memory and resets when the container sleeps.
- **Spend detection that can't be dodged.** Paths are matched after percent-decoding, unreadable
  bodies on spending routes are refused, and any `live` that is not plainly false is counted (the
  server also rejects non-boolean `live`).
- **Per-visitor rate limits.** `X-Forwarded-For` is replaced with `CF-Connecting-IP`, which the
  server trusts (`CLEARWAY_TRUST_PROXY=1`).
- **HTTPS only.**

Live mode switches on only when both `NEBIUS_API_KEY` and `TAVILY_API_KEY` secrets are set.
The `basic` instance (1/4 vCPU, 1 GiB) sleeps after 15 idle minutes. Needs local Docker to build.

```bash
cd deploy/cloudflare
npm install
npm test && npm run check
npx wrangler deploy        # account pinned by CLOUDFLARE_ACCOUNT_ID in the gitignored .env
# secrets, once (values from the repo's .env; never commit them)
npx wrangler secret put NEBIUS_API_KEY
npx wrangler secret put TAVILY_API_KEY
```
