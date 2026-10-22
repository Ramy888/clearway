// Which requests spend Token Factory / Tavily credit, decided the way the server will read them.

// The server decodes percent-escapes before routing (/api/%72un reaches /api/run), so the Worker
// must match on the decoded path, or a live run could start without being counted.
export function decodedPath(pathname: string): string | null {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return null; // malformed escape: refuse rather than guess
  }
}

export type Body = Record<string, unknown>;

/** A JSON object body, or null when it isn't one (the Worker then refuses the request). */
export function parseBody(text: string): Body | null {
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Body) : null;
  } catch {
    return null;
  }
}

export const isSpendRoute = (method: string, path: string) =>
  method === "POST" && (path === "/api/run" || path === "/api/brief");

// The server only accepts a strict boolean for `live`, but count anything that is not plainly
// absent/false: over-counting is released when the server refuses; under-counting would leak spend.
const plainlyOff = (v: unknown) => v === undefined || v === null || v === false;
const empty = (v: unknown) => v === undefined || v === null || (Array.isArray(v) && v.length === 0);

export function spendsCredit(path: string, body: Body): boolean {
  if (plainlyOff(body.live)) return false;
  if (path === "/api/run") return true;
  if (path === "/api/brief") return !empty(body.fix); // only a brief with a fix calls a model
  return false;
}
