"""
Tests for app/agents/llm_client.py.

Run from backend/:
    python scripts/test_llm_client.py            # fake Ollama + fake Gemini servers, no network, no keys
    python scripts/test_llm_client.py --live     # one real call to whatever your .env / environment configures
"""
import json
import os
import sys
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  # noqa: E402

from app.agents import llm_client as llm  # noqa: E402


class Placement(BaseModel):
    item: str
    x: float
    z: float
    rotation_deg: int = 0


class Layout(BaseModel):
    placements: List[Placement]
    notes: Optional[str] = None


GOOD = json.dumps({"placements": [{"item": "Modern Sofa", "x": 1.0, "z": 0.5, "rotation_deg": 90}], "notes": "ok"})
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# ------------------------------------------------------------------ fake servers
class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        self.server.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        step = self.server.script.pop(0) if self.server.script else ("status", 500)
        if step[0] == "status":
            self._send(step[1], {"error": {"message": "scripted"}}, step[2] if len(step) > 2 else {})
        elif step[0] == "ollama":
            self._send(200, {"message": {"role": "assistant", "content": step[1]}})
        elif step[0] == "gemini":
            self._send(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": step[1]}]}}]})

    def _send(self, code, obj, headers=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Fake(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.script: list = []
        self.requests: list = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.server_address[1]


@contextmanager
def env(**kw):
    for k in [k for k in os.environ if k.startswith(("LLM_", "GEMINI_", "OLLAMA_"))]:
        del os.environ[k]
    os.environ["LLM_DOTENV"] = "off"
    os.environ["LLM_RETRY_BASE_DELAY"] = "0.01"
    os.environ.update({k: str(v) for k, v in kw.items()})
    llm.reset_stats()
    yield


ollama, gemini = Fake(), Fake()
LOCAL = dict(LLM_LOCAL_BASE_URL=f"http://127.0.0.1:{ollama.port}", LLM_LOCAL_MODEL="qwen-test", LLM_LOCAL_VISION_MODEL="vl-test")
GEM = dict(LLM_GEMINI_API_KEY="key-123", LLM_GEMINI_MODEL="gemini-test", LLM_GEMINI_BASE_URL=f"http://127.0.0.1:{gemini.port}/v1beta")


def reset():
    ollama.script, ollama.requests, gemini.script, gemini.requests = [], [], [], []


results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + (("   " + str(extra)) if extra else ""))


# ------------------------------------------------------------------ tests
def t_local_valid():
    reset()
    with env(**LOCAL):
        ollama.script = [("ollama", GOOD)]
        out = llm.generate_json("layout", "You arrange furniture.", "Room 4x3", Layout)
        req = ollama.requests[0]["body"]
        check("local: returns a validated object", isinstance(out, Layout) and out.placements[0].item == "Modern Sofa")
        check("local: sends the JSON schema in `format`", "placements" in json.dumps(req.get("format")) and "$ref" not in json.dumps(req["format"]), list(req.keys()))
        check("local: schema also in the system prompt", "JSON schema" in req["messages"][0]["content"])
        check("local: stream off, temperature 0", req["stream"] is False and req["options"]["temperature"] == 0.0)


def t_repair():
    reset()
    with env(**LOCAL):
        ollama.script = [("ollama", "Sure! here it is"), ("ollama", '{"placements": [{"item": "x"}]}'), ("ollama", GOOD)]
        out = llm.generate_json("layout", "s", "u", Layout)
        last = ollama.requests[-1]["body"]["messages"]
        check("repair: succeeds after two bad replies", isinstance(out, Layout))
        check("repair: counted", llm.stats()["repairs"] == 2, llm.stats())
        check("repair: the error is fed back to the model", "not valid" in last[-1]["content"] and "placements.0.x" in last[-1]["content"], last[-1]["content"][:120])


def t_repair_gives_up():
    reset()
    with env(**LOCAL):
        ollama.script = [("ollama", "nope")] * 5
        try:
            llm.generate_json("layout", "s", "u", Layout, max_repairs=1)
            check("repair: raises LLMBadOutput when it never becomes valid", False)
        except llm.LLMBadOutput:
            check("repair: raises LLMBadOutput when it never becomes valid", True)


def t_retry():
    reset()
    with env(**LOCAL):
        ollama.script = [("status", 429), ("status", 503), ("ollama", GOOD)]
        out = llm.generate_json("layout", "s", "u", Layout)
        check("retry: 429 and 503 are retried", isinstance(out, Layout) and len(ollama.requests) == 3 and llm.stats()["retries"] == 2)
        ollama.requests, ollama.script = [], [("status", 401)]
        try:
            llm.generate_json("layout", "s", "u", Layout)
            check("retry: 401 is not retried", False)
        except llm.LLMUnavailable:
            check("retry: 401 is not retried", len(ollama.requests) == 1)


def t_gemini_ok():
    reset()
    with env(**LOCAL, **GEM, LLM_PROVIDER_JUDGE="gemini"):
        gemini.script = [("gemini", GOOD)]
        out = llm.generate_json("judge", "You judge layouts.", "Score this", Layout)
        r = gemini.requests[0]
        check("gemini: used for the agent set to gemini", isinstance(out, Layout) and not ollama.requests)
        check("gemini: path and key header", r["path"] == "/v1beta/models/gemini-test:generateContent" and r["headers"].get("x-goog-api-key") == "key-123", r["path"])
        b = r["body"]
        check("gemini: systemInstruction + JSON mode + user turn",
              "JSON schema" in b["systemInstruction"]["parts"][0]["text"] and b["generationConfig"]["responseMimeType"] == "application/json" and b["contents"][0]["role"] == "user")
        check("gemini: other agents stay local", llm.provider_for("layout") == "local")


def t_gemini_down_falls_back():
    reset()
    with env(**LOCAL, **GEM, LLM_PROVIDER_JUDGE="gemini", LLM_MAX_RETRIES="1"):
        gemini.script = [("status", 429)] * 3
        ollama.script = [("ollama", GOOD)]
        out = llm.generate_json("judge", "s", "u", Layout)
        check("fallback: Gemini 429 -> local answers", isinstance(out, Layout) and len(ollama.requests) == 1)
        check("fallback: counted", llm.stats()["fallbacks"] == 1 and llm.stats()["calls"] == {"local": 1}, llm.stats())


def t_gemini_not_configured():
    reset()
    with env(**LOCAL, LLM_PROVIDER_JUDGE="gemini"):
        ollama.script = [("ollama", GOOD)]
        out = llm.generate_json("judge", "s", "u", Layout)
        check("fallback: no key -> local, and Gemini is never called", isinstance(out, Layout) and not gemini.requests)


def t_gemini_bad_output_falls_back():
    reset()
    with env(**LOCAL, **GEM, LLM_PROVIDER_JUDGE="gemini"):
        gemini.script = [("gemini", "not json")] * 3
        ollama.script = [("ollama", GOOD)]
        out = llm.generate_json("judge", "s", "u", Layout)
        check("fallback: Gemini keeps returning invalid JSON -> local answers", isinstance(out, Layout) and len(gemini.requests) == 3)


def t_fallback_off():
    reset()
    with env(**LOCAL, **GEM, LLM_PROVIDER_JUDGE="gemini", LLM_FALLBACK="off", LLM_MAX_RETRIES="0"):
        gemini.script = [("status", 500)]
        try:
            llm.generate_json("judge", "s", "u", Layout)
            check("fallback off: raises instead of using local", False)
        except llm.LLMUnavailable:
            check("fallback off: raises instead of using local", not ollama.requests)


def t_images():
    reset()
    with env(**LOCAL, **GEM, LLM_PROVIDER_CRITIC="gemini"):
        ollama.script = [("ollama", GOOD)]
        llm.generate_json("layout", "s", "look", Layout, images=[PNG])
        b = ollama.requests[0]["body"]
        check("images: local uses the vision model and sends base64 images", b["model"] == "vl-test" and len(b["messages"][1]["images"]) == 1)
        gemini.script = [("gemini", GOOD)]
        llm.generate_json("critic", "s", "look", Layout, images=[PNG])
        part = gemini.requests[0]["body"]["contents"][0]["parts"][1]
        check("images: Gemini gets inlineData with the right mime type", part["inlineData"]["mimeType"] == "image/png" and part["inlineData"]["data"])


def t_text():
    reset()
    with env(**LOCAL):
        ollama.script = [("ollama", "  The layout is balanced.  ")]
        out = llm.generate_text("judge", "s", "u")
        check("text: returns trimmed free text and sends no schema", out == "The layout is balanced." and "format" not in ollama.requests[0]["body"])


def t_schema():
    with env():
        s = llm._schema_of(Layout)
        flat = json.dumps(s)
        check("schema: no $ref, $defs, anyOf or titles", not any(x in flat for x in ("$ref", "$defs", "anyOf", '"title"')), flat[:140])
        check("schema: nested fields are inlined", s["properties"]["placements"]["items"]["properties"]["item"]["type"] == "string")


def t_env_file():
    with env():
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("# comment\nLLM_TEST_A=plain\nLLM_TEST_B='quoted value'\nLLM_TEST_C=value  # trailing comment\n\nBADLINE\n")
        llm.load_env_file(Path(f.name))
        check("env file: plain, quoted and inline-comment values",
              os.environ.get("LLM_TEST_A") == "plain" and os.environ.get("LLM_TEST_B") == "quoted value" and os.environ.get("LLM_TEST_C") == "value")
        os.environ["LLM_TEST_A"] = "keep"
        llm.load_env_file(Path(f.name))
        check("env file: does not override existing variables", os.environ["LLM_TEST_A"] == "keep")


def run_live():
    class Ping(BaseModel):
        ok: bool
        word: str

    print("configured:", json.dumps(llm.configured()))
    agent = os.environ.get("LLM_LIVE_AGENT", "live")
    print(f"provider for agent '{agent}':", llm.provider_for(agent))
    out = llm.generate_json(agent, "You are a test. Reply with ok=true and word='ping'.", "Reply now.", Ping)
    print("reply:", out)
    print("stats:", json.dumps(llm.stats()))


if __name__ == "__main__":
    if "--live" in sys.argv:
        run_live()
        sys.exit(0)
    for t in (t_local_valid, t_repair, t_repair_gives_up, t_retry, t_gemini_ok, t_gemini_down_falls_back, t_gemini_not_configured,
              t_gemini_bad_output_falls_back, t_fallback_off, t_images, t_text, t_schema, t_env_file):
        t()
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)
