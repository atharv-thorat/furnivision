"""
One place that talks to language models, for every agent.

What it gives each agent:
  * pick the model per agent (local Ollama, or Gemini with fallback to local)
  * force a JSON shape (JSON schema sent to Ollama, schema in the prompt for both)
  * validate the reply against a pydantic model, and ask the model to repair it
  * retry rate limits and network errors with backoff
  * fall back to the local model when Gemini is unavailable
  * count calls, retries, repairs and fallbacks (stats()) for the evaluation harness

Settings (environment variables, or backend/.env):
  LLM_LOCAL_BASE_URL      Ollama address, e.g. http://<host>:11434      (default http://localhost:11434)
  LLM_LOCAL_MODEL         text model                                     (default qwen2.5:7b-instruct)
  LLM_LOCAL_VISION_MODEL  model used when images are sent               (default qwen2.5vl:7b)
  LLM_PROVIDER_DEFAULT    local | gemini                                 (default local)
  LLM_PROVIDER_<AGENT>    per-agent override, e.g. LLM_PROVIDER_JUDGE=gemini
  LLM_GEMINI_API_KEY      key from Google AI Studio. Keep it on the server, never in a web page.
  LLM_GEMINI_MODEL        model id, e.g. gemini-2.5-flash (check AI Studio for current names)
  LLM_FALLBACK            on | off: when Gemini fails, use the local model (default on)
  LLM_MAX_RETRIES         retries per request (default 3)
  LLM_TIMEOUT             seconds per request (default 120)

Only the standard library and pydantic are used.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Base class for everything this module raises."""


class LLMUnavailable(LLMError):
    """A provider cannot be used right now (not configured, network, quota, bad key)."""


class LLMBadOutput(LLMError):
    """The model answered, but not with a valid JSON object even after repair attempts."""


# --------------------------------------------------------------------------- settings
_ENV_LOADED = False


def load_env_file(path: Path) -> int:
    """Read KEY=VALUE lines into os.environ without overriding existing values."""
    n = 0
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if val[:1] in ("'", '"') and val[-1:] == val[:1] and len(val) >= 2:
            val = val[1:-1]
        else:
            val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
        if key and key not in os.environ:
            os.environ[key] = val
            n += 1
    return n


def _load_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if os.environ.get("LLM_DOTENV", "on").lower() == "off":
        return
    load_env_file(Path(__file__).resolve().parents[2] / ".env.llm")  # backend/.env.llm — kept separate from the app's own strict .env


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    _load_dotenv()
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _agent_key(agent: str) -> str:
    return re.sub(r"\W+", "_", agent or "default").upper()


def provider_for(agent: str) -> str:
    p = (_env(f"LLM_PROVIDER_{_agent_key(agent)}") or _env("LLM_PROVIDER_DEFAULT") or "local").lower()
    if p not in ("local", "gemini"):
        log.warning("Unknown LLM provider %r for agent %r; using local", p, agent)
        return "local"
    return p


def configured() -> Dict[str, Any]:
    """What is configured (not whether it is reachable). Safe to show on a status page."""
    return {
        "local_base_url": _env("LLM_LOCAL_BASE_URL") or _env("OLLAMA_BASE_URL") or "http://localhost:11434",
        "local_model": _env("LLM_LOCAL_MODEL") or _env("OLLAMA_MODEL") or "qwen2.5:7b-instruct",
        "gemini_ready": bool((_env("LLM_GEMINI_API_KEY") or _env("GEMINI_API_KEY")) and _env("LLM_GEMINI_MODEL")),
        "fallback": (_env("LLM_FALLBACK", "on") or "on").lower() != "off",
        "default_provider": (_env("LLM_PROVIDER_DEFAULT") or "local").lower(),
    }


# --------------------------------------------------------------------------- stats
_stats_lock = threading.Lock()
_stats: Dict[str, Any] = {"calls": {}, "retries": 0, "repairs": 0, "fallbacks": 0, "failures": 0}


def _bump(key: str, sub: Optional[str] = None) -> None:
    with _stats_lock:
        if sub is None:
            _stats[key] += 1
        else:
            _stats[key][sub] = _stats[key].get(sub, 0) + 1


def stats() -> Dict[str, Any]:
    with _stats_lock:
        return json.loads(json.dumps(_stats))


def reset_stats() -> None:
    with _stats_lock:
        _stats.update({"calls": {}, "retries": 0, "repairs": 0, "fallbacks": 0, "failures": 0})


# --------------------------------------------------------------------------- http
class _HTTPFail(Exception):
    def __init__(self, status: int, body: str, retry_after: Optional[str]):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status, self.body, self.retry_after = status, body, retry_after


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post_json(url: str, payload: dict, headers: dict, timeout: float, direct: bool) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json", **headers})
    opener = _NO_PROXY_OPENER if direct else urllib.request.build_opener()
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise _HTTPFail(e.code, body, e.headers.get("Retry-After"))
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as e:
        raise _HTTPFail(0, str(e), None)


def _with_retries(fn, what: str) -> dict:
    max_retries = int(_env("LLM_MAX_RETRIES", "3") or 3)
    delay = float(_env("LLM_RETRY_BASE_DELAY", "1.0") or 1.0)
    max_wait = float(_env("LLM_MAX_WAIT", "20") or 20)
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except _HTTPFail as e:
            retryable = e.status in (0, 408, 429, 500, 502, 503, 504)
            if not retryable or attempt == max_retries:
                raise LLMUnavailable(f"{what}: {e}")
            wait = delay
            if e.retry_after:
                try:
                    wait = float(e.retry_after)
                except ValueError:
                    pass
            _bump("retries")
            time.sleep(min(wait, max_wait))
            delay = min(delay * 2, max_wait)
    raise LLMUnavailable(f"{what}: gave up")  # pragma: no cover


# --------------------------------------------------------------------------- schema + json helpers
def _schema_of(model_cls: Type[BaseModel]) -> dict:
    raw = model_cls.model_json_schema() if hasattr(model_cls, "model_json_schema") else model_cls.schema()
    return simplify_schema(raw)


def simplify_schema(schema: dict) -> dict:
    """Inline $ref, drop titles/defaults, turn Optional[X] into X. Keeps the schema small and portable."""
    defs = schema.get("$defs") or schema.get("definitions") or {}

    def resolve(node: Any, depth: int = 0) -> Any:
        if isinstance(node, list):
            return [resolve(x, depth) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            if depth > 8:
                return {"type": "object"}
            target = defs.get(str(node["$ref"]).split("/")[-1], {})
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return {**resolve(target, depth + 1), **resolve(extra, depth + 1)}
        out: Dict[str, Any] = {}
        for k, v in node.items():
            if k in ("$defs", "definitions", "title", "default"):
                continue
            if k == "anyOf" and isinstance(v, list):
                non_null = [x for x in v if not (isinstance(x, dict) and x.get("type") == "null")]
                if len(non_null) == 1:
                    out.update(resolve(non_null[0], depth))
                    continue
            out[k] = resolve(v, depth)
        return out

    return resolve(schema)


def _schema_instructions(schema: dict) -> str:
    return (
        "Reply with ONLY one JSON object that matches this JSON schema. "
        "No markdown fences, no commentary before or after.\n" + json.dumps(schema, separators=(",", ":"))
    )


def _extract_json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE).strip()
    try:
        return json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a != -1 and b > a:
            return json.loads(t[a : b + 1])
        raise ValueError("reply contains no JSON object")


def _validate(model_cls: Type[T], obj: Any) -> T:
    return model_cls.model_validate(obj) if hasattr(model_cls, "model_validate") else model_cls.parse_obj(obj)


def _short_error(e: Exception) -> str:
    try:
        return "; ".join(f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in e.errors()[:5])  # type: ignore[attr-defined]
    except Exception:
        return str(e)[:300]


# --------------------------------------------------------------------------- providers
def _mime_of(data: bytes) -> str:
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF":
        return "image/webp"
    return "image/png"


def _call_local(messages: List[dict], schema: Optional[dict], temperature: float, timeout: float, has_images: bool) -> str:
    base = (_env("LLM_LOCAL_BASE_URL") or _env("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    text_model = _env("LLM_LOCAL_MODEL") or _env("OLLAMA_MODEL") or "qwen2.5:7b-instruct"
    model = (_env("LLM_LOCAL_VISION_MODEL") or "qwen2.5vl:7b") if has_images else text_model
    out = []
    for m in messages:
        d = {"role": m["role"], "content": m["content"]}
        if m.get("_images"):
            d["images"] = [base64.b64encode(b).decode("ascii") for b in m["_images"]]
        out.append(d)
    payload: Dict[str, Any] = {"model": model, "messages": out, "stream": False, "options": {"temperature": temperature}}
    if schema is not None:
        payload["format"] = schema
    resp = _with_retries(lambda: _post_json(f"{base}/api/chat", payload, {}, timeout, direct=True), f"local model {model}")
    try:
        return resp["message"]["content"]
    except (KeyError, TypeError):
        raise LLMUnavailable(f"local model {model}: unexpected reply shape")


def _call_gemini(messages: List[dict], json_mode: bool, temperature: float, timeout: float) -> str:
    key = _env("LLM_GEMINI_API_KEY") or _env("GEMINI_API_KEY")
    model = _env("LLM_GEMINI_MODEL")
    if not key or not model:
        raise LLMUnavailable("Gemini is not configured (LLM_GEMINI_API_KEY and LLM_GEMINI_MODEL)")
    base = (_env("LLM_GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        parts: List[dict] = [{"text": m["content"]}]
        for img in m.get("_images") or []:
            parts.append({"inlineData": {"mimeType": _mime_of(img), "data": base64.b64encode(img).decode("ascii")}})
        contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
    gen_cfg: Dict[str, Any] = {"temperature": temperature}
    if json_mode:
        gen_cfg["responseMimeType"] = "application/json"
    payload: Dict[str, Any] = {"contents": contents, "generationConfig": gen_cfg}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    resp = _with_retries(
        lambda: _post_json(f"{base}/models/{model}:generateContent", payload, {"x-goog-api-key": key}, timeout, direct=False),
        f"Gemini {model}",
    )
    try:
        parts = resp["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        reason = (resp.get("promptFeedback") or {}).get("blockReason") if isinstance(resp, dict) else None
        raise LLMUnavailable(f"Gemini returned no text{f' (blocked: {reason})' if reason else ''}")
    if not text.strip():
        raise LLMUnavailable("Gemini returned empty text")
    return text


def _order(agent: str) -> List[str]:
    primary = provider_for(agent)
    order = [primary]
    if primary == "gemini" and (_env("LLM_FALLBACK", "on") or "on").lower() != "off":
        order.append("local")
    return order


def _messages(system: str, user: str, images: Optional[List[bytes]]) -> List[dict]:
    first_user: Dict[str, Any] = {"role": "user", "content": user}
    if images:
        first_user["_images"] = list(images)
    return [{"role": "system", "content": system}, first_user]


# --------------------------------------------------------------------------- public api
def generate_json(
    agent: str,
    system: str,
    user: str,
    model_cls: Type[T],
    *,
    images: Optional[List[bytes]] = None,
    temperature: float = 0.0,
    max_repairs: int = 2,
    timeout: Optional[float] = None,
) -> T:
    """Ask the model for a JSON object shaped like `model_cls`; return a validated instance.

    Raises LLMBadOutput or LLMUnavailable only after every allowed provider has failed.
    """
    tmo = float(timeout or _env("LLM_TIMEOUT", "120") or 120)
    schema = _schema_of(model_cls)
    errors: List[str] = []
    for i, provider in enumerate(_order(agent)):
        if i > 0:
            _bump("fallbacks")
            log.warning("agent %s: falling back to %s (%s)", agent, provider, errors[-1] if errors else "")
        msgs = _messages(system.rstrip() + "\n\n" + _schema_instructions(schema), user, images)
        try:
            for attempt in range(max_repairs + 1):
                if provider == "gemini":
                    text = _call_gemini(msgs, True, temperature, tmo)
                else:
                    text = _call_local(msgs, schema, temperature, tmo, bool(images))
                try:
                    result = _validate(model_cls, _extract_json(text))
                    _bump("calls", provider)
                    return result
                except (ValueError, ValidationError) as e:
                    problem = _short_error(e)
                    if attempt == max_repairs:
                        raise LLMBadOutput(f"{provider}: invalid output after {max_repairs} repairs: {problem}")
                    _bump("repairs")
                    msgs = msgs + [
                        {"role": "assistant", "content": text[:4000]},
                        {"role": "user", "content": f"That reply was not valid: {problem}\nReply again with ONLY the corrected JSON object."},
                    ]
        except LLMError as e:
            errors.append(str(e))
    _bump("failures")
    raise (LLMBadOutput if any("invalid output" in e for e in errors) else LLMUnavailable)("; ".join(errors))


def generate_text(
    agent: str,
    system: str,
    user: str,
    *,
    images: Optional[List[bytes]] = None,
    temperature: float = 0.2,
    timeout: Optional[float] = None,
) -> str:
    """Free-text answer (explanations, critiques). Same provider order, retries and fallback."""
    tmo = float(timeout or _env("LLM_TIMEOUT", "120") or 120)
    errors: List[str] = []
    for i, provider in enumerate(_order(agent)):
        if i > 0:
            _bump("fallbacks")
        msgs = _messages(system, user, images)
        try:
            text = _call_gemini(msgs, False, temperature, tmo) if provider == "gemini" else _call_local(msgs, None, temperature, tmo, bool(images))
            _bump("calls", provider)
            return text.strip()
        except LLMError as e:
            errors.append(str(e))
    _bump("failures")
    raise LLMUnavailable("; ".join(errors))
