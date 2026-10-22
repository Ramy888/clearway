"""Research: Tavily-backed clause text and contractor price cards for the ledger/UI.

Cards are display evidence only. They never reach the Auditor (its signature has no
place for them), and no threshold is ever read from them — code numbers live in
rules.py. A price shown is quoted from a cited page with its URL, never generated.
"""
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import llm  # noqa: F401  (loads the repo .env)
from .catalogue import CATALOGUE

TAVILY_URL = "https://api.tavily.com/search"


class ResearchError(Exception):
    pass


@dataclass(frozen=True)
class Card:
    kind: str                  # "clause" | "price"
    subject: str               # clause id or fix id
    title: str
    url: str
    snippet: str
    price_range: Optional[str] = None   # quoted from the cited page, if it states one
    price_quote: Optional[str] = None   # the sentence the range came from, for context


def _post(payload: dict, key: str, timeout: int = 30) -> dict:
    if not key:
        raise ResearchError("TAVILY_API_KEY not set (add it to .env)")
    req = urllib.request.Request(
        TAVILY_URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ResearchError(f"HTTP {e.code}: {e.read().decode()[:200]}") from None
    except urllib.error.URLError as e:
        raise ResearchError(f"network error: {e.reason}") from None


def search(query: str, *, max_results: int = 3, depth: str = "basic",
           post: Optional[Callable] = None) -> List[dict]:
    data = (post or _post)(
        {"query": query, "max_results": max_results, "search_depth": depth},
        os.environ.get("TAVILY_API_KEY", ""),
    )
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in data.get("results", [])]


_CUR = r"(?:EGP|E£|LE|USD|US\$|\$|€|£)"
_PRICE = re.compile(rf"{_CUR}\s?\d[\d,.]*(?:\s?(?:-|–|to)\s?{_CUR}?\s?\d[\d,.]*)?", re.I)


_COST_VERB = re.compile(r"\b(?:pay|pays|paid|cost|costs|price|priced|prices|charge|charges)\b", re.I)


# "$1,000 retrofit to a $5,000": a range with a few words between the two figures.
_AMOUNT = rf"{_CUR}\s?\d[\d,]*(?:\.\d+)?"
_SPACED_RANGE = re.compile(rf"({_AMOUNT})(?:\s+\S+){{0,3}}?\s+(?:to|-|–)\s+(?:an?\s+)?({_AMOUNT})", re.I)


def _figure(sentence: str):
    """(display text, is_range) for the price stated in one sentence, or None."""
    m = _PRICE.search(sentence)
    if not m:
        return None
    text = m.group(0).strip().rstrip(".,")
    if re.search(r"-|–|\bto\b", text):
        return text, True
    spaced = _SPACED_RANGE.search(sentence)
    if spaced:
        return f"{spaced.group(1)} to {spaced.group(2)}", True
    return text, False


def _price_range(text: str):
    """(range, sentence): a stated range beats a single figure (often a worst case), then a
    sentence about paying, then the earliest."""
    best = None
    for i, s in enumerate(re.split(r"(?<=[.!?])\s+", text or "")):
        fig = _figure(s)
        if fig:
            key = (fig[1], bool(_COST_VERB.search(s)), -i)
            if best is None or key > best[0]:
                best = (key, fig[0], s.strip())
    return (best[1], best[2]) if best else (None, None)


def _first(results: List[dict]) -> dict:
    return results[0] if results else {"title": "", "url": "", "content": ""}


def clause_card(clause: str, *, post: Optional[Callable] = None) -> Card:
    r = _first(search(f"{clause} accessible door requirement text", post=post))
    return Card("clause", clause, r["title"], r["url"], r["content"][:280])


# A source must be about doors/walls at all before we quote a number from it.
_DOMAIN = re.compile(r"\b(?:door|doors|doorway|doorways|hinge|hinges|threshold|thresholds"
                     r"|wall|walls|frame|frames)\b", re.I)


def _relevant(r: dict) -> bool:
    return bool(_DOMAIN.search(f"{r['title']} {r['content']}"))


def price_card(fix_id: str, region: str = "Cairo, Egypt", *,
               post: Optional[Callable] = None) -> Optional[Card]:
    """A cited price for this fix, or None when no relevant source turns up."""
    fix = CATALOGUE.get(fix_id)
    phrase = fix.phrase if fix and fix.phrase else fix_id.replace("_", " ")
    results = [r for r in search(f"cost to {phrase} for wheelchair access {region}", post=post)
               if _relevant(r)]
    if not results:
        return None
    for r in results:  # prefer a source that actually states a price
        pr, quote = _price_range(r["content"])
        if pr:
            return Card("price", fix_id, r["title"], r["url"], r["content"][:280], pr, quote)
    r = _first(results)
    return Card("price", fix_id, r["title"], r["url"], r["content"][:280])


class TavilyResearch:
    """Evidence provider for orchestrator.run. Failures degrade to no card."""

    def __init__(self, post: Optional[Callable] = None, region: str = "Cairo, Egypt"):
        self.post, self.region = post, region

    def clause(self, clause: str) -> Optional[Card]:
        try:
            return clause_card(clause, post=self.post)
        except ResearchError:
            return None

    def price(self, fix_id: str) -> Optional[Card]:
        try:
            return price_card(fix_id, self.region, post=self.post)
        except ResearchError:
            return None
