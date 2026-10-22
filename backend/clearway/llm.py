"""Token Factory client: thin OpenAI-compatible wrapper over the Nemotron tiers.

Lean by design — stdlib only, no SDK. Models only propose, narrate and explain;
nothing here decides. Nano is eu-north1, Super/Ultra are us-central1, so each tier
carries its own base URL.

shortcut: no retry/streaming yet; add when the UI needs token streaming.
"""
import json
import os
import pathlib
import urllib.error
import urllib.request

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load the repo .env into the environment (does not override existing vars)."""
    p = _REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env()

MODELS = {
    "nano": (os.environ.get("NANO_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
             os.environ.get("NANO_BASE_URL", "https://api.tokenfactory.nebius.com/v1")),
    "super": (os.environ.get("SUPER_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
              os.environ.get("SUPER_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1")),
    "ultra": (os.environ.get("ULTRA_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b"),
              os.environ.get("ULTRA_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1")),
}


class LLMError(Exception):
    pass


def chat(tier, messages, *, max_tokens=256, temperature=0.2, timeout=60):
    """Return (content, usage_dict). `tier` is 'nano' | 'super' | 'ultra'."""
    if tier not in MODELS:
        raise LLMError(f"unknown tier: {tier}")
    model, base = MODELS[tier]
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise LLMError("NEBIUS_API_KEY not set (add it to .env)")
    payload = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read().decode()[:300]}") from None
    except urllib.error.URLError as e:
        raise LLMError(f"network error: {e.reason}") from None
    choice = data["choices"][0]
    content = choice["message"].get("content")
    if not content:
        # Nemotron tiers reason first; a small max_tokens can be spent before any answer.
        raise LLMError(f"empty content (finish_reason={choice.get('finish_reason')}); "
                       f"raise max_tokens — usage={data.get('usage')}")
    return content, data.get("usage", {})


if __name__ == "__main__":  # one-shot smoke test (a live Nano call)
    content, usage = chat(
        "nano", [{"role": "user", "content": "Reply with exactly: CLEARWAY online"}],
        max_tokens=512,
    )
    print("NANO:", content.strip())
    print("usage:", usage)
