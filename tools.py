"""
tools.py
--------
Tool specifications (in the OpenAI/Anthropic function-calling format) and the
Python dispatcher that routes each call through `r_helpers/run_mainger.R`.

Bridge protocol
---------------
Each tool serializes its arguments to JSON and pipes them through Rscript:

    echo '{"tool":"detect_regime","args":{...},"session":{...}}' \
        | Rscript r_helpers/run_mainger.R

The R script returns a single JSON object on stdout. This keeps the Python
side language-agnostic — swap the R bridge for a Python port of mainger
later without touching the agent loop.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Tool specifications (vendor-neutral; both Anthropic and OpenAI accept them) #
# --------------------------------------------------------------------------- #
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "detect_regime",
        "description": (
            "Classify the sharing regime as 'full', 'partial', or 'restricted' "
            "based on which summaries the user has supplied."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "has_internal_individual_data": {"type": "boolean"},
                "has_internal_marginal_only":   {"type": "boolean"},
                "has_external_theta":           {"type": "boolean"},
                "has_external_sigma2":          {"type": "boolean"},
                "has_reference_panel":          {"type": "boolean"},
            },
            "required": [
                "has_internal_individual_data",
                "has_internal_marginal_only",
                "has_external_theta",
                "has_external_sigma2",
                "has_reference_panel",
            ],
        },
    },
    {
        "name": "compute_eta_bound",
        "description": (
            "Return the upper bound eta_star of the beneficial range for the "
            "given regime, using the loaded session data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "regime": {"type": "string", "enum": ["full", "partial", "restricted"]},
            },
            "required": ["regime"],
        },
    },
    {
        "name": "check_concordance",
        "description": (
            "Evaluate the spectral advantage A(eta) and return a "
            "concordant / discordant / indeterminate verdict. Full regime only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eta": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["eta"],
        },
    },
    {
        "name": "fit_integrated_estimator",
        "description": (
            "Fit the integrated estimator at the chosen eta and return "
            "coefficients, MSE estimates, and diagnostic fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eta":    {"type": "number", "minimum": 0, "maximum": 1},
                "regime": {"type": "string", "enum": ["full", "partial", "restricted"]},
                "tuning": {
                    "type": "string",
                    "enum": ["fixed", "auto", "cv", "eaic"],
                    "description": "Use the supplied eta directly, or override via CV/eAIC inside the bound.",
                },
            },
            "required": ["eta", "regime"],
        },
    },
]


# --------------------------------------------------------------------------- #
# Dispatch                                                                     #
# --------------------------------------------------------------------------- #
R_SCRIPT = Path(__file__).parent / "r_helpers" / "run_mainger.R"


class ToolError(RuntimeError):
    pass


def call_tool(name: str, args: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    """Execute one tool call by invoking the R bridge.

    `session` is the canonicalized data dict produced by data_io.load_session.
    The R bridge writes it to a temp RDS once per agent run; here we just pass
    a path reference so we don't re-serialize matrices on every call.
    """
    payload = {"tool": name, "args": args, "session_path": session["_path"]}
    proc = subprocess.run(
        ["Rscript", str(R_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise ToolError(
            f"R bridge failed (tool={name}):\nSTDERR:\n{proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ToolError(
            f"R bridge returned non-JSON (tool={name}):\n{proc.stdout[:500]}"
        ) from e
