"""Provider-agnostic LLM call. Same interface for Claude CLI, local Ollama, and OpenAI-compatible APIs.

    from coach.llm import complete
    out = complete("claude-haiku", system, user, schema=None)  # -> dict(text, json, usage, cost_usd, latency_s, model)

Swap models by name (coach/models.yaml) so evaluation and later service routing use the same code path.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = str(Path.home() / ".local" / "bin" / "claude")


def load_models():
    return yaml.safe_load((ROOT / "coach" / "models.yaml").read_text("utf-8"))["models"]


def _env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _parse_json(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    s, e = t.find("{"), t.rfind("}")
    try:
        return json.loads(t[s:e + 1]) if s >= 0 else None
    except json.JSONDecodeError:
        return None


def _claude_cli(cfg, system, user, schema):
    args = [CLAUDE, "-p", system, "--model", cfg["model"], "--output-format", "json", "--tools", "",
            "--strict-mcp-config", "--no-session-persistence"]
    if schema:
        args += ["--json-schema", json.dumps(schema)]
    p = subprocess.run(args, input=user, capture_output=True, text=True, timeout=900, cwd="/tmp")
    out = json.loads(p.stdout)
    u = out.get("usage", {})
    usage = {"input": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
             "output": u.get("output_tokens") or 0}
    data = out.get("structured_output") or _parse_json(out.get("result"))
    return out.get("result"), data, usage, out.get("total_cost_usd")


def _http_json(url, body, headers, timeout=900):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _ollama(cfg, system, user, schema):
    body = {"model": cfg["model"], "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"num_ctx": cfg.get("num_ctx", 8192), "temperature": cfg.get("temperature", 0.2)}}
    if schema:
        body["format"] = schema  # Ollama structured outputs accept a JSON schema
    out = _http_json(cfg.get("host", "http://localhost:11434") + "/api/chat", body, {})
    text = out["message"]["content"]
    usage = {"input": out.get("prompt_eval_count", 0), "output": out.get("eval_count", 0)}
    return text, _parse_json(text), usage, 0.0  # local: no API fee (hardware cost tracked separately)


def _openai_compat(cfg, system, user, schema):
    _env()
    key = os.environ.get(cfg["api_key_env"], "")
    if not key:
        raise RuntimeError(f"{cfg['api_key_env']} not set in .env")
    body = {"model": cfg["model"], "temperature": cfg.get("temperature", 0.2),
            "messages": [{"role": "system", "content": system + ("\n반드시 JSON 하나만 출력." if schema else "")},
                         {"role": "user", "content": user}]}
    if schema:
        body["response_format"] = {"type": "json_object"}
    out = _http_json(cfg["base_url"].rstrip("/") + "/chat/completions", body, {"Authorization": f"Bearer {key}"})
    text = out["choices"][0]["message"]["content"]
    u = out.get("usage", {})
    usage = {"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)}
    price = cfg.get("price_per_mtok") or {}
    cost = None
    if price.get("input") is not None and price.get("output") is not None:
        cost = usage["input"] / 1e6 * price["input"] + usage["output"] / 1e6 * price["output"]
    return text, _parse_json(text), usage, cost


PROVIDERS = {"claude_cli": _claude_cli, "ollama": _ollama, "openai_compat": _openai_compat}


def complete(name, system, user, schema=None):
    cfg = load_models()[name]
    t0 = time.time()
    text, data, usage, cost = PROVIDERS[cfg["provider"]](cfg, system, user, schema)
    return {"model": name, "text": text, "json": data, "usage": usage, "cost_usd": cost,
            "latency_s": round(time.time() - t0, 1)}
