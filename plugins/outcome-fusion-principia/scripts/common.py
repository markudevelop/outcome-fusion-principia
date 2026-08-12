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

# Usage/latency of the most recent successful DeepSeek call, for cost telemetry.
_LAST_CALL: dict[str, Any] = {}

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
    # Write UTF-8 bytes directly so a non-ASCII char in the payload (e.g. an
    # arrow the model echoed) can't crash the hook on Windows' cp1252 stdout.
    # Falls back to ASCII-escaped JSON, which is still valid and encoding-safe.
    data = json.dumps(obj, ensure_ascii=False)
    try:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write((data + "\n").encode("utf-8"))
            buf.flush()
        else:
            print(json.dumps(obj, ensure_ascii=True))
    except Exception:
        print(json.dumps(obj, ensure_ascii=True))


def continue_decision(reason: str, autocontinue: bool) -> dict[str, Any]:
    """Build the Stop-hook output that keeps Claude working.

    autocontinue=True returns a top-level ``decision: block`` which FORCES Claude
    to continue in the same turn (no user re-prompt) — this is the "stop
    stopping" behaviour. autocontinue=False falls back to non-blocking
    additionalContext (guidance seen next turn). Continuation is still bounded by
    OUTCOME_FUSION_MAX_CONTINUES in the gate.
    """
    if autocontinue:
        return {"decision": "block", "reason": reason, "suppressOutput": True}
    return {
        "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": reason},
        "suppressOutput": True,
    }


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


# Spans that are quoting/illustrating a word rather than asserting it: fenced
# code, inline code, and quoted strings. Stripped before lazy detection.
_QUOTE_OR_CODE = re.compile(r"```.*?```|`[^`]*`|\"[^\"]*\"|'[^']*'", re.S)
# A line that is talking *about* the forbidden words (a rule or instruction),
# not making the claim itself.
_RULE_CONTEXT = re.compile(
    r"never say|do(?:n'?t| not) say|avoid saying|stop saying|the word|scenario|example|quoting|flagged?",
    re.I,
)


def contains_lazy_impossible(text: str) -> bool:
    """True only when the agent itself asserts impossibility.

    Quoting the words, showing them in code, or discussing the rule must NOT
    trip this — those false positives forced spurious release-gate FAILs.
    """
    if not text:
        return False
    cleaned = _QUOTE_OR_CODE.sub(" ", text)
    flagged_lines = [
        ln for ln in cleaned.splitlines()
        if any(re.search(p, ln.lower()) for p in LAZY_IMPOSSIBLE_PATTERNS)
    ]
    # A real refusal is prose the agent asserts: not meta-discussion of the
    # words, and not a markdown table cell (illustrative, e.g. eval scenarios).
    return any(
        not _RULE_CONTEXT.search(ln) and "|" not in ln
        for ln in flagged_lines
    )


def should_skip_prompt(prompt: str) -> bool:
    p = (prompt or "").strip().lower()
    if not p:
        return True
    if p.startswith("/") and not p.startswith("/outcome-fusion"):
        return True
    if any(tag in p for tag in ["nofusion", "no fusion", "skip outcome fusion", "disable outcome fusion"]):
        return True
    return False


# --- intent router -----------------------------------------------------------
# A question is a question. Claude Opus 5 expands scope on its own judgment, and
# this plugin used to amplify that: EVERY prompt — including "what does this do?"
# — was compiled into a full "execute release ready" mission and then judged by a
# 3-vote release gate that forced continuation. That turns an answer into an
# unasked-for implementation and burns a mission compile + 3 judge calls per
# question. Routing on intent is the fix: build prompts get the full apparatus,
# question prompts get an answer-only instruction and no gate.

# Imperative verbs that mean "change something". Presence of any of these makes
# the prompt a BUILD prompt even if it is phrased as a question ("can you add X?").
_BUILD_VERBS = re.compile(
    r"\b(implement|build|create|add|write|fix|refactor|rewrite|migrate|port|"
    r"deploy|ship|publish|commit|push|merge|install|upgrade|update|change|"
    r"modify|edit|remove|delete|drop|rename|replace|optimi[sz]e|improve|"
    r"clean\s?up|set\s?up|configure|generate|make|run|execute|backtest|"
    r"benchmark|profile|debug|patch|revert|bump|scaffold|wire|hook\s?up|"
    r"integrate|automate|harden|refit|retrain|tune|"
    # Action verbs that carry work even when phrased as "can you ...?".
    # Added after replaying 474 real prompts from this project and auditing every
    # question-mode classification by hand.
    r"brute[\s-]?force|sweep|screen|scan|harvest|backfill|export|import|"
    r"plot|chart|render|train|fit|simulate|replay|audit|review|validate|"
    r"verify|check|investigate|diagnose|reproduce|repro|measure|rerun|"
    r"re-?run|kick\s?off|land|set|move|use|apply|enable|disable|switch|swap|"
    r"store|save|sync|track|reduce|increase|lower|raise|resize|test|retest)\b",
    re.I,
)

# Phrases that state a want or a directive. These beat any interrogative shape:
# "i need this on the website" and "ok lets use the new one" are work orders even
# though they read like conversation.
_IMPERATIVE_MARKERS = re.compile(
    r"\b(let'?s|lets|i want|i'd like|i would like|i need|we need|we should|"
    r"should be|must be|make sure|go ahead|please do|do it|do this|do that|"
    r"do all|do both|do everything|carry on|proceed)\b",
    re.I,
)

# A reported defect is a work order, not a question, however it is punctuated:
# "again it seems we had an issue with the publisher?" wants a fix, not an essay.
_PROBLEM_MARKERS = re.compile(
    r"\b(bug|broken|is wrong|shows? wrong|isn'?t working|is not working|"
    r"not working|does ?n'?t work|do ?n'?t work|failed|failing|fails|error|"
    r"issue|crash(?:ed|ing)?|stuck|hangs?|missing|wrong|"
    r"no signal|not updated|did ?n'?t update|out of date|stale)\b",
    re.I,
)

# Bare "do X" is an order ("do it all", "do 2% for her"); "do you/we/..." is a
# question. Everything after `do ` that is not one of these subjects is an order.
_DO_QUESTION_SUBJECTS = re.compile(r"^do\s+(you|we|i|they|he|she|these|those|any|most|all\s+of)\b", re.I)

# Interrogative openers / shapes that mean "tell me", not "do it".
_QUESTION_OPENERS = re.compile(
    r"^(what|why|how|when|where|which|who|whose|is|are|was|were|does|did|"
    r"can|could|should|would|will|has|have|had|am|explain|describe|compare|"
    r"tell\s+me|walk\s+me|any\s+idea|thoughts)\b",
    re.I,
)

INTENT_BUILD = "build"
INTENT_QUESTION = "question"


def classify_intent(prompt: str) -> str:
    """Classify a raw user prompt as a question or a build request.

    Deliberately biased toward BUILD: a build prompt misread as a question loses
    the mission and the gate (soft failure), while a question misread as a build
    triggers unrequested implementation (the failure mode we are removing). Any
    imperative verb anywhere in the prompt wins.

    Explicit overrides: a prompt starting with ``build:`` / ``do:`` forces build,
    ``q:`` / ``ask:`` forces question. ``OUTCOME_FUSION_INTENT_ROUTER=0`` disables
    routing entirely (pre-0.7.0 behaviour: everything is a build).
    """
    p = (prompt or "").strip()
    if not p:
        return INTENT_BUILD
    low = p.lower()
    if low.startswith(("build:", "do:", "task:")):
        return INTENT_BUILD
    if low.startswith(("q:", "ask:", "question:")):
        return INTENT_QUESTION
    if not env_bool("OUTCOME_FUSION_INTENT_ROUTER", True):
        return INTENT_BUILD
    if _BUILD_VERBS.search(low) or _IMPERATIVE_MARKERS.search(low) or _PROBLEM_MARKERS.search(low):
        return INTENT_BUILD
    if low.startswith("do ") and not _DO_QUESTION_SUBJECTS.match(low):
        return INTENT_BUILD
    if _QUESTION_OPENERS.match(low) or low.endswith("?"):
        return INTENT_QUESTION
    return INTENT_BUILD


def write_turn_mode(wdir: Path, intent: str, prompt: str) -> None:
    """Record this turn's intent so the Stop hook knows whether to gate."""
    safe_write(
        wdir / "turn_mode.json",
        json.dumps({"intent": intent, "prompt_sha": sha(prompt or ""), "ts": time.time()}, ensure_ascii=False),
    )


def read_turn_mode(wdir: Path) -> str:
    """Intent of the current turn. Defaults to build so the gate stays on."""
    try:
        data = json.loads((wdir / "turn_mode.json").read_text(encoding="utf-8"))
        intent = str(data.get("intent") or "").strip().lower()
        return intent if intent in {INTENT_BUILD, INTENT_QUESTION} else INTENT_BUILD
    except Exception:
        return INTENT_BUILD


# --- Claude Opus 5 operating block -------------------------------------------
# Sourced from Anthropic's "Prompting Claude Opus 5" guide (scope and
# over-verification, narration, self-correction, deliverable length, subagent
# spawning) plus the three CLAUDE.md blocks from productcompass.pm's
# "How to Heal Claude Opus 5" (act don't ask / a question is a question / done
# means done). Where the two disagree, Anthropic's guide wins: it says to REMOVE
# explicit self-verification and re-check instructions because Opus 5 already
# verifies itself and the instructions compound into wasted tokens. This plugin
# keeps verification pressure only where it is out-of-band (the DeepSeek release
# gate, a different model judging after the fact), never as a "check yourself
# again" instruction to Claude.
OPUS5_OPERATING_BLOCK = """
Operating mode (tuned for Claude Opus 5):
- Scope: deliver what was asked at the scope intended. Make routine judgment calls yourself; check in only when different readings would lead to materially different work. If the request looks mistaken or a better approach exists, say so in one sentence and continue with the task as asked rather than quietly narrowing, widening, or transforming it. Stop short of actions clearly beyond what was asked.
- Done means done: finish every requested item. If five things were asked for, deliver five, not four and a report. If one part is genuinely blocked, finish the rest and name that blocker in one specific sentence.
- Act, don't ask: run reversible, inexpensive steps (reading, searching, drafting, testing) without asking. Ask only before actions that reach an audience, cost real money, or cannot be undone.
- Narration: one sentence before the first tool call, brief updates only when something important turns up or the direction changes, and a final message that leads with the outcome.
- Corrections: correct an earlier statement only when the error changes the user's code, conclusions, or decisions. Otherwise fix it and move on without narrating it.
- Written deliverables: match document length to what the task needs. No filler sections, redundant summaries, or boilerplate.
- Delegation: use a subagent only for large, genuinely independent, parallelizable work. Do not delegate what you can finish in a handful of tool calls, and do not spawn subagents to double-check your own work.
- Self-verification: you already check your own work, so do not add extra re-verification passes on top of it. The release gate in this plugin is a separate out-of-band judge; it is not your job to duplicate it.
""".strip()

QUESTION_MODE_CONTEXT = """
Outcome Fusion classified this turn as a QUESTION, not a build request.

A question is a request for information, not a mandate to implement.
1. Answer it. Investigate as much as you need: read, search, run analyses, compute the numbers. Doing the work required to answer is expected.
2. Do not change the project: no implementing, refactoring, renaming, or "improving" anything the user did not ask for.
3. If you spot work worth doing, name it in one line and let the user decide.
4. Lead with the answer and keep it as short as the question deserves.

No mission was compiled and the release gate is off for this turn, so nothing will
force you to keep working. Prefix a prompt with `build:` to force full mission mode.
""".strip()


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


def call_deepseek(system: str, user: str, *, max_tokens: int = 4000, temperature: float = 0.15, json_mode: bool = False, timeout: int = 120, effort: str | None = None) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    # Effort is per-call. Anthropic's Opus 5 guidance — use low/medium liberally
    # as the primary cost lever and reserve high for the demanding pass — applies
    # to the judge too: mission compilation is a rewrite, the release gate is the
    # hard judgement, so they get different defaults.
    body: dict[str, Any] = {
        "model": get_model(),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": redact(user, limit=180000)}],
        "output_config": {"effort": effort or os.getenv("OUTCOME_FUSION_EFFORT", "high")},
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
    t0 = time.time()
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
                global _LAST_CALL
                _LAST_CALL = {
                    "model": body.get("model"),
                    "usage": data.get("usage") or {},
                    "latency_ms": int((time.time() - t0) * 1000),
                }
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
    effort: str | None = None,
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
        raw = call_deepseek(system, prompt, max_tokens=max_tokens, temperature=temperature, json_mode=True, timeout=timeout, effort=effort)
        data = parse_json_loose(raw)
        if data and all(k in data for k in require_keys):
            return data, raw
        prompt = user + "\n\nReturn ONLY a single valid JSON object containing every required key. No prose, no markdown fences, no trailing text."
    return data, raw


def last_call_metric() -> dict[str, Any]:
    return dict(_LAST_CALL)


def log_metric(wdir: Path, label: str, extra: dict[str, Any] | None = None) -> None:
    """Append one cost/latency record (tokens + ms) for the last DeepSeek call."""
    m = last_call_metric()
    usage = m.get("usage") or {}
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": label,
        "model": m.get("model"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "latency_ms": m.get("latency_ms"),
    }
    if extra:
        record.update(extra)
    try:
        safe_append(wdir / "metrics.jsonl", json.dumps(record, ensure_ascii=False) + "\n", max_chars=200000)
    except Exception:
        pass


def summarize_metrics(wdir: Path) -> dict[str, Any]:
    """Aggregate the per-call telemetry in metrics.jsonl into a session total."""
    text = safe_read(wdir / "metrics.jsonl", limit=500000)
    calls = tin = tout = lat = 0
    by_label: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        calls += 1
        tin += int(r.get("input_tokens") or 0)
        tout += int(r.get("output_tokens") or 0)
        lat += int(r.get("latency_ms") or 0)
        lbl = str(r.get("label") or "?")
        by_label[lbl] = by_label.get(lbl, 0) + 1
    return {
        "calls": calls,
        "input_tokens": tin,
        "output_tokens": tout,
        "total_tokens": tin + tout,
        "avg_latency_ms": round(lat / calls) if calls else 0,
        "by_label": by_label,
    }


def evidence_already_recorded(wdir: Path, cmd: str) -> bool:
    """True if this exact verification command is already in the recent proof tail.

    Stops the proof ledger from filling with one identical Evidence block per
    repeated test/lint/build invocation.
    """
    if not cmd:
        return True
    return f"`{cmd}`" in safe_read(wdir / "proof.md", limit=6000)


# Distinct evaluation lenses for self-consistency voting. Diversity of
# perspective — not re-rolling the same prompt — is what the Mixture-of-Agents
# literature says drives the gain (see docs/MODEL_FUSION.md).
GATE_LENSES = [
    "",  # vote 0: the full doctrine, no extra lens
    "For this pass, weight EVIDENCE most: is every important claim verified, sourced, tested, or calculated?",
    "For this pass, weight COMPLETENESS and closure most: what would the user's 'is there anything else?' reveal as missing?",
    "For this pass, weight SIMPLICITY most: what is unnecessary, overbuilt, or should be removed before adding more?",
    "For this pass, weight CORRECTNESS most: is anything actually wrong, inaccurate, or broken?",
]


def vote_lenses(n: int) -> list[str]:
    """Return n distinct judging lenses (cycling) for perspective-diverse voting."""
    if n <= 1:
        return [""]
    return [GATE_LENSES[i % len(GATE_LENSES)] for i in range(n)]


def aggregate_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine N independent judge verdicts by self-consistency (majority).

    Ties or any BLOCKED resolve conservatively (do not PASS on a split). The
    returned review keeps the worst-case blocker and unions the action lists so
    nothing a single judge flagged is lost.
    """
    reviews = [r for r in reviews if isinstance(r, dict) and r.get("verdict")]
    if not reviews:
        return {}
    if len(reviews) == 1:
        return reviews[0]
    verdicts = [str(r.get("verdict", "")).upper() for r in reviews]
    counts = {v: verdicts.count(v) for v in set(verdicts)}
    n = len(verdicts)
    # PASS only with a strict majority of PASS and no BLOCKED present.
    if counts.get("PASS", 0) > n / 2 and "BLOCKED" not in verdicts:
        winner = "PASS"
    elif "BLOCKED" in verdicts and counts.get("PASS", 0) <= n / 2:
        winner = "BLOCKED"
    else:
        winner = "FAIL"
    base = next((r for r in reviews if str(r.get("verdict", "")).upper() == winner), reviews[0])
    merged = dict(base)
    merged["verdict"] = winner
    merged["votes"] = counts
    scores = [r.get("progress_score") for r in reviews if isinstance(r.get("progress_score"), (int, float))]
    if scores:
        merged["progress_score"] = round(sum(scores) / len(scores))
    actions: list[str] = []
    for r in reviews:
        for a in (r.get("next_actions") or []):
            if a not in actions:
                actions.append(a)
    if actions:
        merged["next_actions"] = actions
    return merged


def git_status_and_diff(cwd: Path, diff_limit: int | None = None) -> tuple[str, str, str]:
    status = run_cmd("git status --short", cwd, timeout=15, limit=20000)
    diff_cmd = "git diff -- . ':(exclude).git' ':(exclude)node_modules' ':(exclude).next' ':(exclude)dist' ':(exclude)build' ':(exclude).ai/outcome_fusion/tool_log.md'"
    limit = diff_limit if diff_limit is not None else env_int("OUTCOME_FUSION_MAX_DIFF_CHARS", 40000)
    diff = run_cmd(diff_cmd, cwd, timeout=30, limit=limit)
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
    lesson = redact(text.strip(), limit=5000)
    # Dedup: don't append a lesson identical to one already recorded recently.
    # Without this the same fallback lesson piled up dozens of times.
    if lesson in safe_read(wdir / "memory.md", limit=8000):
        return
    entry = f"\n\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n{lesson}\n"
    safe_append(wdir / "memory.md", entry, max_chars=80000)
    # Also keep repo-level memory shared across future sessions in the same repo.
    try:
        root = wdir.parent.parent if wdir.parent.name == "sessions" else wdir
        if lesson not in safe_read(root / "memory.md", limit=8000):
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
