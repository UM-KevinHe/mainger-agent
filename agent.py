"""
agent.py
--------
Two entry points:
  - run_agent(...)            : synchronous; returns final dict. Used by CLI.
  - run_agent_streaming(...)  : generator; yields event dicts as they happen.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterator

import yaml
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from data_io import build_session, persist_session
from llm_client import LLMResponse, make_client
from tools import TOOL_SPECS, ToolError, call_tool

ROOT = Path(__file__).parent
SKILL_PATH    = ROOT / "skill.md"
TEMPLATE_DIR  = ROOT / "templates"


def load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def render_one(env: Environment, template_name: str, payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return env.get_template(template_name).render(**payload)
    return str(payload)


def render_artifacts(filled: dict[str, Any]) -> dict[str, str]:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), keep_trailing_newline=True)
    return {
        "report.md":      render_one(env, "report.md.j2",      filled.get("report", "")),
        "analysis.R":     render_one(env, "code.R.j2",         filled.get("code", "")),
        "explanation.md": render_one(env, "explanation.md.j2", filled.get("explanation", "")),
    }


def _balanced_json_at(s: str, start: int) -> str | None:
    if start >= len(s) or s[start] != "{":
        return None
    depth, in_string, escape = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if in_string:
            if c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def _find_fenced_blocks(text: str, lang_pattern: str) -> list[str]:
    rx = re.compile(rf"```\s*({lang_pattern})\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
    return [m.group(2) for m in rx.finditer(text)]


_ANY_FENCE_RX = re.compile(r"```\s*([A-Za-z0-9_+\-]*)\s*\n(.*?)\n```", re.DOTALL)


def _all_fenced_blocks(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).lower(), m.group(2)) for m in _ANY_FENCE_RX.finditer(text)]


def extract_final(text: str) -> dict | None:
    if not text:
        return None

    json_blocks: list[str] = []
    for m in re.finditer(r"```json\s*", text, re.IGNORECASE):
        block = _balanced_json_at(text, m.end())
        if block:
            json_blocks.append(block)

    for block in json_blocks:
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and {"report", "code", "explanation"}.issubset(obj.keys()):
            return obj

    merged: dict[str, Any] = {}
    for block in json_blocks:
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            for k in ("report", "code", "explanation"):
                if k in obj and k not in merged:
                    merged[k] = obj[k]

    if "code" not in merged:
        r_blocks = _find_fenced_blocks(text, r"r|R")
        if r_blocks:
            merged["code"] = r_blocks[0].strip()

    if "explanation" not in merged:
        md_blocks = _find_fenced_blocks(text, r"markdown|md|text|plaintext|plain|txt")
        if md_blocks:
            merged["explanation"] = md_blocks[0].strip()

    if "explanation" not in merged:
        skip_langs = {"json", "r"}
        for lang, content in _all_fenced_blocks(text):
            if lang in skip_langs:
                continue
            stripped = content.strip()
            if stripped:
                merged["explanation"] = stripped
                break

    if {"report", "code", "explanation"}.issubset(merged.keys()):
        return merged

    for m in re.finditer(r"\{", text):
        block = _balanced_json_at(text, m.start())
        if block is None:
            continue
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and {"report", "code", "explanation"}.issubset(obj.keys()):
            return obj

    return None


def run_agent_streaming(
    session: dict,
    user_message: str,
    cfg: dict,
    api_key: str | None = None,
    base_url: str | None = None,
    prior_messages: list[dict] | None = None,
) -> Iterator[dict]:
    """Yield one event dict per step. Pass `base_url` to use a non-default
    endpoint for OpenAI-compatible vendors."""
    try:
        client = make_client(
            vendor=cfg["vendor"], model=cfg["model"],
            max_tokens=cfg.get("max_tokens", 4096),
            temperature=cfg.get("temperature", 0.0),
            api_key=api_key,
            base_url=base_url,
        )
    except Exception as e:
        import traceback as tb
        yield {"type": "error", "error": str(e), "traceback": tb.format_exc()}
        return

    yield {"type": "started", "vendor": cfg["vendor"], "model": cfg["model"]}

    skill = load_skill()
    system = (
        f"{skill}\n\n"
        f"Session metadata (read-only):\n{json.dumps(session['_metadata'], indent=2)}"
    )

    messages: list[dict] = list(prior_messages or [])
    messages.append({"role": "user", "content": user_message})

    trace: list[dict] = []
    max_iters = cfg.get("max_tool_iterations", 8)

    for step in range(max_iters):
        yield {"type": "llm_call", "step": step}

        try:
            resp: LLMResponse = client.complete(messages, TOOL_SPECS, system)
        except Exception as e:
            import traceback as tb
            yield {"type": "error", "error": f"LLM call failed: {e}", "traceback": tb.format_exc()}
            return

        trace.append({
            "step": step, "text": resp.text,
            "tool_calls": resp.tool_calls, "stop_reason": resp.stop_reason,
        })

        if resp.text:
            yield {"type": "assistant_text", "step": step, "text": resp.text}

        messages.append(client.format_assistant_with_tools(resp))

        if not resp.tool_calls:
            final = extract_final(resp.text or "")
            if final is None:
                yield {"type": "final_text", "text": resp.text or "",
                       "trace": trace, "messages": messages}
            else:
                yield {"type": "final", "final": final,
                       "trace": trace, "messages": messages}
            return

        for call in resp.tool_calls:
            yield {"type": "tool_call", "step": step,
                   "name": call["name"], "args": call["args"], "id": call["id"]}
            try:
                bridge_out = call_tool(call["name"], call["args"], session)
                result = (bridge_out.get("result")
                          if bridge_out.get("ok")
                          else {"error": bridge_out.get("error")})
            except ToolError as e:
                result = {"error": str(e)}
            trace.append({"step": step, "tool_result": {"name": call["name"], "result": result}})
            yield {"type": "tool_result", "step": step,
                   "name": call["name"], "result": result, "id": call["id"]}
            messages.append(client.format_tool_result(call["id"], call["name"], result))

    yield {"type": "error",
           "error": f"Hit max_tool_iterations={max_iters} without final answer.",
           "traceback": ""}


def run_agent(
    session: dict, user_message: str, cfg: dict,
    api_key: str | None = None, base_url: str | None = None,
    prior_messages: list[dict] | None = None,
) -> dict:
    final, trace, messages, text = None, None, None, None
    err = None
    for event in run_agent_streaming(session, user_message, cfg,
                                     api_key=api_key, base_url=base_url,
                                     prior_messages=prior_messages):
        if event["type"] == "final":
            final = event["final"]; trace = event["trace"]; messages = event["messages"]
        elif event["type"] == "final_text":
            text = event["text"]; trace = event["trace"]; messages = event["messages"]
        elif event["type"] == "error":
            err = event
    if err:
        raise RuntimeError(f"{err.get('error')}\n{err.get('traceback', '')}")
    return {"final": final, "text": text, "trace": trace or [], "messages": messages or []}


def _safe_write_json(path: Path, obj: Any) -> None:
    try:
        path.write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False),
                        encoding="utf-8")
    except Exception as e:
        print(f"  (warning: could not write {path.name}: {e})")


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="mainger-agent (online)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--external-coef", required=True)
    ap.add_argument("--external-sigma")
    ap.add_argument("--reference-sigma")
    ap.add_argument("--sigma2-int", type=float)
    ap.add_argument("--sigma2-ext", type=float)
    ap.add_argument("--n-ext", type=int)
    ap.add_argument("--regime", choices=["full", "partial", "restricted"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out-dir", default="runs/latest")
    ap.add_argument("--vendor", default=None, help="Override config.yaml vendor")
    ap.add_argument("--model",  default=None, help="Override config.yaml model")
    ap.add_argument("--base-url", default=None, help="Optional base URL for OpenAI-compatible vendors")
    ap.add_argument("--message", default="Please analyze my data and produce the integration report, code, and explanation.")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.vendor: cfg["vendor"] = args.vendor
    if args.model:  cfg["model"]  = args.model

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/4] Loading data into session ...")
    session = build_session(
        internal_path=args.input,
        external_coef_path=args.external_coef,
        external_sigma_path=args.external_sigma,
        reference_sigma_path=args.reference_sigma,
        sigma2_int=args.sigma2_int,
        sigma2_ext=args.sigma2_ext,
        n_ext=args.n_ext,
    )
    session = persist_session(session, out_dir)
    print(f"  metadata: {json.dumps(session['_metadata'])}")

    print(f"[2/4] Running agent (vendor={cfg['vendor']}, model={cfg['model']}) ...")
    user_msg = args.message
    if args.regime:
        user_msg += f"\n(I believe this is the {args.regime} regime.)"
    out = run_agent(session, user_msg, cfg, base_url=args.base_url)

    _safe_write_json(out_dir / "trace.json", out["trace"])
    if out["final"]:
        _safe_write_json(out_dir / "final.json", out["final"])

    print("[3/4] Rendering artifacts ...")
    if out["final"]:
        artifacts = render_artifacts(out["final"])
        print(f"[4/4] Writing outputs to {out_dir} ...")
        for name, content in artifacts.items():
            (out_dir / name).write_text(
                content if isinstance(content, str) else str(content),
                encoding="utf-8",
            )
    else:
        print(f"[4/4] No artifacts produced; conversational response only.")

    print("Done.")


if __name__ == "__main__":
    main()
