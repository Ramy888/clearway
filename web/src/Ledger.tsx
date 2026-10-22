import { safeHref } from "./model";
import type { Card, LedgerEvent } from "./types";

const ACTION_LABEL: Record<string, string> = {
  load: "loaded the home",
  drive: "drove the route",
  cite: "cited the code",
  propose: "proposed a fix",
  refuse: "REFUSED",
  accept: "accepted",
  "approve-pending": "waiting for you",
  escalate: "escalated",
};

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function Evidence({ card }: { card: Card }) {
  const href = safeHref(card.url);
  const text = card.price_quote ?? card.snippet;
  const body = (
    <>
      <span className="card-kind">{card.kind === "clause" ? "Code text" : "Price"}</span>
      {card.price_range && <strong className="card-price">{card.price_range}</strong>}
      <span className="card-text">{text.length > 150 ? `${text.slice(0, 150)}…` : text}</span>
      {href && <span className="card-src">{host(href)}</span>}
    </>
  );
  return href ? (
    <a className="card" href={href} target="_blank" rel="noopener noreferrer">
      {body}
    </a>
  ) : (
    <div className="card">{body}</div>
  );
}

export function Ledger({ events }: { events: LedgerEvent[] }) {
  return (
    <ol className="ledger" aria-label="Agent ledger">
      {events.map((e, n) => (
        <li
          key={n}
          data-action={e.action}
          className={`ev ${e.action} ${e.ok ? "ok" : "bad"}`}
          style={{ animationDelay: `${n * 90}ms` }}
        >
          <div className="ev-head">
            <span className={`badge a-${e.agent.toLowerCase()}`}>{e.agent}</span>
            <span className="ev-action">{ACTION_LABEL[e.action] ?? e.action}</span>
          </div>
          <p className="ev-detail">{e.detail}</p>
          {e.card && <Evidence card={e.card} />}
        </li>
      ))}
    </ol>
  );
}
