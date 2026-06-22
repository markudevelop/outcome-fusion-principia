from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PLUGIN_SLUG = "outcome_fusion"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_BASE_URL = "https://api.deepseek.com/anthropic"

LAZY_IMPOSSIBLE_PATTERNS = [
    r"\bimpossible\b",
    r"\bnot possible\b",
    r"\bcan't\b",
    r"\bcannot\b",
    r"\bwon't work\b",
    r"\bnot realistic\b",
    r"\bno edge\b",
    r"\bthere is no way\b",
    r"\bunachievable\b",
    r"\bnever works\b",
    r"\bdoesn't exist\b",
]

SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|refresh[_-]?token|bearer)\s*[:=]\s*['\"]?[^'\"\s]+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)authorization:\s*bearer\s+[a-z0-9._\-]+"), "Authorization: Bearer <REDACTED>"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "sk-<REDACTED>"),
    (re.compile(r"ghp_[A-Za-z0-9_]{20,}"), "ghp_<REDACTED>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "<PRIVATE_KEY_REDACTED>"),
]


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def json_stdout(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def get_api_key() -> str:
    return (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
        or ""
    )


def get_model() -> str:
    return os.getenv("OUTCOME_FUSION_MODEL", DEFAULT_MODEL)


def get_base_url() -> str:
    return os.getenv("DEEPSEEK_ANTHROPIC_BASE_URL", os.getenv("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")


def cwd_from_hook(payload: dict[str, Any]) -> Path:
    return Path(payload.get("cwd") or os.getenv("CLAUDE_PROJECT_DIR") or os.getcwd()).expanduser().resolve()


def workspace_root_dir(cwd: Path) -> Path:
    p = cwd / ".ai" / PLUGIN_SLUG
    p.mkdir(parents=True, exist_ok=True)
    (p / "sessions").mkdir(parents=True, exist_ok=True)
    return p


def _clean_session_part(value: str, limit: int = 80) -> str:
    clean = "".join(c if (c.isalnum() or c in "._-") else "_" for c in value.strip())
    clean = clean.strip("._-")
    return (clean or "unknown")[:limit]


def session_key_from_payload(payload: dict[str, Any] | None, cwd: Path) -> str:
    payload = payload or {}
    root = cwd / ".ai" / PLUGIN_SLUG
    session = str(payload.get("session_id") or "").strip()
    if session and session.lower() not in {"unknown", "none", "null"}:
        return "sid_" + _clean_session_part(session, 96)

    transcript = str(payload.get("transcript_path") or "").strip()
    if transcript:
        return "tx_" + sha(transcript)

    # Some hook payloads may omit session fields. In that case keep using the active session.
    current = root / "current_session.txt"
    if current.exists():
        cur = safe_read(current, limit=200).strip()
        if cur:
            return _clean_session_part(cur, 120)

    return "cwd_" + sha(str(cwd))


def workspace_dir(cwd: Path, payload: dict[str, Any] | None = None) -> Path:
    root = workspace_root_dir(cwd)
    key = session_key_from_payload(payload, cwd)
    p = root / "sessions" / key
    p.mkdir(parents=True, exist_ok=True)
    safe_write(root / "current_session.txt", key)
    meta = {
        "session_key": key,
        "cwd": str(cwd),
        "session_id": (payload or {}).get("session_id"),
        "transcript_path": (payload or {}).get("transcript_path"),
        "hook_event_name": (payload or {}).get("hook_event_name"),
        "source": (payload or {}).get("source"),
        "updated_at": time.time(),
    }
    safe_write(p / "_session_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return p


def find_resume_workspace(cwd: Path, payload: dict[str, Any] | None = None) -> Path | None:
    root = workspace_root_dir(cwd)
    payload = payload or {}
    wanted_transcript = str(payload.get("transcript_path") or "").strip()
    wanted_session = str(payload.get("session_id") or "").strip()
    sessions_root = root / "sessions"
    candidates = [p for p in sessions_root.iterdir() if p.is_dir()] if sessions_root.exists() else []

    # Strong match first: same transcript or same session id in metadata, preferring sessions that already have a mission.
    strong_matches: list[Path] = []
    for p in candidates:
        try:
            meta = json.loads((p / "_session_meta.json").read_text(encoding="utf-8"))
        except Exception:
            meta = {}
        if wanted_transcript and str(meta.get("transcript_path") or "") == wanted_transcript:
            strong_matches.append(p)
            continue
        if wanted_session and str(meta.get("session_id") or "") == wanted_session:
            strong_matches.append(p)
    with_mission_matches = [p for p in strong_matches if (p / "mission.md").exists()]
    if with_mission_matches:
        return max(with_mission_matches, key=lambda x: (x / "mission.md").stat().st_mtime)
    if strong_matches:
        return strong_matches[0]

    # Fallback to current session pointer.
    current = safe_read(root / "current_session.txt", limit=200).strip()
    if current and (sessions_root / current).exists():
        return sessions_root / current

    # Last resort: newest session with mission.
    with_mission = [p for p in candidates if (p / "mission.md").exists()]
    if with_mission:
        return max(with_mission, key=lambda x: (x / "mission.md").stat().st_mtime)
    return None


def workspace_display_path(wdir: Path) -> str:
    return str(wdir)


def mirror_latest(wdir: Path, filename: str, text: str | None = None) -> None:
    # Convenience mirrors only. Session folder is source of truth.
    try:
        root = wdir.parent.parent if wdir.parent.name == "sessions" else wdir
        src = wdir / filename
        content = text if text is not None else safe_read(src, limit=500000)
        if content:
            safe_write(root / ("latest_" + filename), content)
    except Exception:
        pass


def session_paths_block(wdir: Path) -> str:
    return f"""Session workspace: {wdir}
Mission: {wdir / 'mission.md'}
Proof ledger: {wdir / 'proof.md'}
Review: {wdir / 'review.md'}
Closure: {wdir / 'closure.md'}
Tool log: {wdir / 'tool_log.md'}"""


def plugin_data_dir(payload: dict[str, Any] | None = None) -> Path:
    root = os.getenv("CLAUDE_PLUGIN_DATA")
    if root:
        p = Path(root).expanduser()
    else:
        p = Path.home() / ".claude" / PLUGIN_SLUG
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_read(path: Path, limit: int = 60000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if len(text) > limit:
        return text[-limit:]
    return text


def safe_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_append(path: Path, text: str, max_chars: int = 160000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = safe_read(path, limit=max_chars)
    safe_write(path, (old + text)[-max_chars:])


def redact(text: str, limit: int | None = None) -> str:
    if not text:
        return ""
    out = text
    for pattern, replacement in SECRET_PATTERNS:
        out = pattern.sub(replacement, out)
    if limit is not None and len(out) > limit:
        out = out[-limit:]
    return out


def run_cmd(cmd: str, cwd: Path, timeout: int = 20, limit: int = 30000) -> str:
    try:
        out = subprocess.check_output(cmd, cwd=str(cwd), shell=True, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except Exception as e:
        out = str(e)
    return redact(out, limit=limit)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def safe_format(template: str, **values: Any) -> str:
    """Token substitution that ignores literal braces.

    `str.format` treats every `{...}` as a field, so a template that embeds a
    JSON example (e.g. the release-gate schema) raises KeyError. This only
    replaces the exact named placeholders and leaves all other braces intact.
    """
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def _balanced_json_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of every top-level balanced {...} block.

    Brace-aware and string-aware so braces inside JSON string values don't throw
    off the depth count.
    """
    spans: list[tuple[int, int]] = []
    depth = 0
    start: int | None = None
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append((start, i + 1))
    return spans


def parse_json_loose(text: str) -> dict[str, Any]:
    """Extract a JSON object even when the model prefixes it with reasoning prose.

    Reasoning models (e.g. DeepSeek at high effort) often emit a thinking
    preamble before the JSON. A greedy ``{.*}`` regex starts at the first brace —
    which may be a stray brace inside that prose — and fails to parse. Instead we
    find every balanced top-level object and return the last one that parses
    (the answer normally comes after the reasoning).
    """
    if not text:
        return {}
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    for s, e in reversed(_balanced_json_spans(text)):
        try:
            obj = json.loads(text[s:e])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def contains_lazy_impossible(text: str) -> bool:
    hay = (text or "").lower()
    return any(re.search(p, hay) for p in LAZY_IMPOSSIBLE_PATTERNS)


def should_skip_prompt(prompt: str) -> bool:
    p = (prompt or "").strip().lower()
    if not p:
        return True
    if p.startswith("/") and not p.startswith("/outcome-fusion"):
        return True
    if any(tag in p for tag in ["nofusion", "no fusion", "skip outcome fusion", "disable outcome fusion"]):
        return True
    return False


def project_signals(cwd: Path) -> str:
    parts: list[str] = []
    markers = [
        "package.json", "pnpm-lock.yaml", "bun.lockb", "yarn.lock", "package-lock.json",
        "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "Makefile",
        "next.config.js", "next.config.ts", "vite.config.ts", "tsconfig.json", "pytest.ini"
    ]
    found = [m for m in markers if (cwd / m).exists()]
    if found:
        parts.append("Files: " + ", ".join(found))
    pkg = cwd / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            if scripts:
                parts.append("npm scripts: " + ", ".join(sorted(scripts.keys())[:25]))
            deps = sorted(list((data.get("dependencies") or {}).keys()) + list((data.get("devDependencies") or {}).keys()))
            if deps:
                parts.append("deps: " + ", ".join(deps[:40]))
        except Exception:
            pass
    pyproject = cwd / "pyproject.toml"
    if pyproject.exists():
        txt = safe_read(pyproject, limit=12000)
        tools = re.findall(r"^\[tool\.([^\]]+)\]", txt, flags=re.M)
        if tools:
            parts.append("python tools: " + ", ".join(sorted(set(tools))[:25]))
    try:
        top = [p.name + ("/" if p.is_dir() else "") for p in sorted(cwd.iterdir(), key=lambda x: x.name.lower()) if p.name not in {".git", "node_modules", ".next", "dist", "build"}]
        parts.append("top level: " + ", ".join(top[:50]))
    except Exception:
        pass
    return "\n".join(parts) or "No project signals detected."


def recent_transcript_text(path_str: str, limit_chars: int = 50000) -> str:
    if not path_str:
        return ""
    path = Path(path_str).expanduser()
    if not path.exists():
        return ""
    raw = safe_read(path, limit=300000)
    lines = raw.splitlines()[-180:]
    picked: list[str] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        if not isinstance(msg, dict):
            msg = obj if isinstance(obj, dict) else {}
        role = msg.get("role") or obj.get("role") or obj.get("type") or "event"
        content = msg.get("content") or obj.get("content")
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        chunks.append(item.get("text", ""))
                    elif item.get("type") == "tool_use":
                        chunks.append(f"tool_use {item.get('name')}: {item.get('input')}")
            content = "\n".join(chunks)
        if isinstance(content, str) and content.strip():
            picked.append(f"{role}: {content.strip()}")
    text = redact("\n\n".join(picked), limit=limit_chars)
    return text


def extract_text_from_anthropic_response(data: dict[str, Any]) -> str:
    content = data.get("content", [])
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "thinking"}:
                texts.append(str(item.get("text") or item.get("thinking") or ""))
        return "\n".join(t for t in texts if t.strip())
    return ""


def call_deepseek(system: str, user: str, *, max_tokens: int = 4000, temperature: float = 0.15, json_mode: bool = False, timeout: int = 120) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    body: dict[str, Any] = {
        "model": get_model(),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": redact(user, limit=180000)}],
        "output_config": {"effort": os.getenv("OUTCOME_FUSION_EFFORT", "high")},
    }
    if json_mode:
        body["messages"][0]["content"] += "\n\nReturn valid JSON only."
    req = Request(
        get_base_url() + "/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    # One bounded retry by default so a single transient connect timeout does
    # not silently degrade the whole hook to a heuristic fallback. Kept small so
    # total wall time stays inside the hook timeout budget.
    retries = max(0, env_int("OUTCOME_FUSION_RETRIES", 1))
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
                return extract_text_from_anthropic_response(data).strip()
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")[:2000]
            last_err = RuntimeError(f"DeepSeek HTTP {e.code}: {detail}")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_err
        except URLError as e:
            last_err = RuntimeError(f"DeepSeek network error: {e}")
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_err
    raise last_err or RuntimeError("DeepSeek call failed")


def call_deepseek_json(
    system: str,
    user: str,
    *,
    max_tokens: int = 4000,
    temperature: float = 0.1,
    timeout: int = 120,
    require_keys: list[str] | None = None,
) -> tuple[dict[str, Any], str]:
    """Call DeepSeek expecting JSON, and retry once if the reply does not parse.

    Without this, a single malformed/truncated JSON reply collapses the gate to
    the keyword heuristic — a measurably worse judge. One stricter re-ask
    recovers most parse failures before any fallback. Network errors are left to
    propagate so the caller's existing fallback handles them.

    Returns (parsed_dict, raw_text); parsed_dict is {} only if both attempts
    failed to produce the required keys.
    """
    require_keys = require_keys or []
    attempts = max(1, env_int("OUTCOME_FUSION_JSON_RETRIES", 1) + 1)
    prompt = user
    raw = ""
    data: dict[str, Any] = {}
    for attempt in range(attempts):
        raw = call_deepseek(system, prompt, max_tokens=max_tokens, temperature=temperature, json_mode=True, timeout=timeout)
        data = parse_json_loose(raw)
        if data and all(k in data for k in require_keys):
            return data, raw
        prompt = user + "\n\nReturn ONLY a single valid JSON object containing every required key. No prose, no markdown fences, no trailing text."
    return data, raw


def git_status_and_diff(cwd: Path) -> tuple[str, str, str]:
    status = run_cmd("git status --short", cwd, timeout=15, limit=20000)
    diff_cmd = "git diff -- . ':(exclude).git' ':(exclude)node_modules' ':(exclude).next' ':(exclude)dist' ':(exclude)build' ':(exclude).ai/outcome_fusion/tool_log.md'"
    diff = run_cmd(diff_cmd, cwd, timeout=30, limit=100000)
    return status, diff, sha(status + diff)


def default_mission(prompt: str, cwd: Path) -> str:
    signals = project_signals(cwd)
    return f"""# Mission
Execute the user's request fully and release ready: {prompt.strip()}

# Method
Use first principles. Define the real constraint, remove non essential parts, test what can be tested, and never accept vague impossibility claims.

# Assumptions
Make practical assumptions and continue. Do not ask low value questions. Execute, verify, and report. Only stop for true blockers that cannot be safely resolved inside the local repo.

# Project signals
{signals}

# Non negotiable rules
1. Do not lower the ambition.
2. Never say impossible, cannot, not realistic, or no edge unless checked or reduced to a specific blocker.
3. Never guess when you can inspect, search, run, calculate, test, backtest, or verify.
4. Remove unnecessary parts before adding complexity.
5. No fake implementation, no placeholder TODO, no broken imports, no silent failures.
6. Keep proof in the session-specific proof ledger injected by the plugin, not a global proof file.

# Definition of done
The main outcome works end to end. Relevant tests or checks were run. Claims are supported by evidence. Remaining uncertainty is explicit. The final response separates done, verified, failed, uncertain, and next best test.
"""


def append_memory(wdir: Path, text: str) -> None:
    if not text or not text.strip():
        return
    entry = f"\n\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n{redact(text.strip(), limit=5000)}\n"
    safe_append(wdir / "memory.md", entry, max_chars=80000)
    # Also keep repo-level memory shared across future sessions in the same repo.
    try:
        root = wdir.parent.parent if wdir.parent.name == "sessions" else wdir
        safe_append(root / "memory.md", entry, max_chars=120000)
    except Exception:
        pass


def combined_memory(wdir: Path, limit: int = 30000) -> str:
    root = wdir.parent.parent if wdir.parent.name == "sessions" else wdir
    session_memory = safe_read(wdir / "memory.md", limit=limit)
    root_memory = safe_read(root / "memory.md", limit=limit)
    if session_memory and root_memory and session_memory != root_memory:
        return ("# Session memory\n" + session_memory + "\n\n# Project memory\n" + root_memory)[-limit:]
    return session_memory or root_memory


def make_state_path(payload: dict[str, Any], cwd: Path) -> Path:
    key = session_key_from_payload(payload, cwd)
    clean = _clean_session_part(cwd.name + "_" + key, 140)
    return plugin_data_dir(payload) / f"{clean}_state.json"


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"continues": 0, "last_diff_hash": "", "same_diff_count": 0, "last_blocker": ""}


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = time.time()
    safe_write(path, json.dumps(state, ensure_ascii=False, indent=2))


def summarize_hook_tool(payload: dict[str, Any], limit: int = 8000) -> str:
    event = payload.get("hook_event_name") or "unknown"
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or payload.get("error") or ""
    if not isinstance(tool_response, str):
        try:
            tool_response = json.dumps(tool_response, ensure_ascii=False)[:limit]
        except Exception:
            tool_response = str(tool_response)
    return redact(f"Event: {event}\nTool: {tool}\nInput: {json.dumps(tool_input, ensure_ascii=False)[:4000]}\nOutput/Error: {tool_response[:limit]}\n", limit=limit + 5000)
