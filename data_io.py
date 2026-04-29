"""
data_io.py
----------
Load user inputs into a canonical session dict and persist it as an RDS file
that the R bridge reads.

Supported formats per input:
  - Internal individual data:  CSV, Parquet
  - External coefficients:     CSV, Parquet (2 columns: variable, estimate)
  - Sigma matrices:            CSV, Parquet (square, no header)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


# --------------------------------------------------------------------------- #
# Format detection                                                             #
# --------------------------------------------------------------------------- #
def _read_table(path: str | Path) -> pd.DataFrame:
    """Load a tabular file by extension. Supports CSV and Parquet."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(p)
    if suffix in {".csv", ".tsv", ".txt"}:
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(p, sep=sep)
    # Fallback: try CSV
    return pd.read_csv(p)


def _read_matrix(path: str | Path) -> list[list[float]]:
    """Load a numeric matrix (no header). Supports CSV and Parquet."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p, header=None)
    return df.to_numpy().tolist()


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #
def load_individual(path: str | Path) -> dict[str, Any]:
    """Load individual-level (X, Y) data. First column = response."""
    df = _read_table(path)
    y = df.iloc[:, 0].to_numpy()
    x = df.iloc[:, 1:].to_numpy()
    names = df.columns[1:].tolist()
    return {
        "X_int": x.tolist(),
        "Y_int": y.tolist(),
        "predictor_names": names,
        "n_int": int(len(y)),
    }


def load_external_coef(path: str | Path) -> dict[str, Any]:
    """External coefficients as a 2-column file: variable, estimate."""
    df = _read_table(path)
    if df.shape[1] < 2:
        raise ValueError("external coef file must have columns: variable, estimate")
    coef = dict(zip(df.iloc[:, 0].astype(str), df.iloc[:, 1].astype(float)))
    return {"beta_ext_named": coef}


def align_external(beta_ext_named: dict[str, float], predictor_names: list[str]) -> list[float]:
    """Order external coefs to match internal predictor order; missing -> 0."""
    return [float(beta_ext_named.get(n, 0.0)) for n in predictor_names]


# --------------------------------------------------------------------------- #
# Session assembly                                                             #
# --------------------------------------------------------------------------- #
def build_session(
    *,
    internal_path: str | Path | None = None,
    internal_format: str | None = None,           # accepted but no longer required
    external_coef_path: str | Path | None = None,
    external_sigma_path: str | Path | None = None,
    reference_sigma_path: str | Path | None = None,
    sigma2_int: float | None = None,
    sigma2_ext: float | None = None,
    n_ext: int | None = None,
    manual: dict[str, Any] | None = None,
    base_session: dict[str, Any] | None = None,   # for multi-turn updates
) -> dict[str, Any]:
    """Assemble a session dict from whatever the user has.

    If `base_session` is provided, fields from new uploads OVERRIDE existing
    fields, but other keys carry forward. This is what lets a chat-message
    upload partially update the session.
    """
    s: dict[str, Any] = {}
    if base_session:
        s = {k: v for k, v in base_session.items() if not k.startswith("_")}

    if manual:
        s.update(manual)

    if internal_path:
        s.update(load_individual(internal_path))

    if external_coef_path:
        ext = load_external_coef(external_coef_path)
        names = s.get("predictor_names")
        if names:
            s["beta_ext"] = align_external(ext["beta_ext_named"], names)
        else:
            s["beta_ext"] = list(ext["beta_ext_named"].values())

    if external_sigma_path:
        s["Sigma_ext"] = _read_matrix(external_sigma_path)
    if reference_sigma_path:
        s["Sigma_ref"] = _read_matrix(reference_sigma_path)

    if sigma2_int is not None: s["sigma2_int"] = sigma2_int
    if sigma2_ext is not None: s["sigma2_ext"] = sigma2_ext
    if n_ext      is not None: s["n_ext"]      = int(n_ext)

    return s


# --------------------------------------------------------------------------- #
# Persistence (JSON -> RDS via R)                                              #
# --------------------------------------------------------------------------- #
R_PERSIST_SCRIPT = r"""suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
in_path  <- args[1]
out_path <- args[2]

s <- fromJSON(in_path, simplifyVector = TRUE, simplifyMatrix = TRUE)

coerce_matrix <- function(x) {
  if (is.null(x)) return(NULL)
  if (is.matrix(x)) return(matrix(as.numeric(x), nrow = nrow(x), ncol = ncol(x)))
  if (is.data.frame(x)) return(as.matrix(x))
  if (is.list(x)) return(do.call(rbind, lapply(x, as.numeric)))
  if (is.numeric(x)) return(matrix(x, nrow = 1))
  stop("Cannot coerce field to matrix")
}
for (nm in c("X_int", "Sigma_int", "Sigma_ext", "Sigma_ref")) {
  if (!is.null(s[[nm]])) s[[nm]] <- coerce_matrix(s[[nm]])
}
for (nm in c("Y_int", "beta_int", "beta_ext", "r_int")) {
  if (!is.null(s[[nm]])) s[[nm]] <- as.numeric(s[[nm]])
}
for (nm in c("sigma2_int", "sigma2_ext")) {
  if (!is.null(s[[nm]])) s[[nm]] <- as.numeric(s[[nm]])
}
for (nm in c("n_int", "n_ext")) {
  if (!is.null(s[[nm]])) s[[nm]] <- as.integer(s[[nm]])
}

saveRDS(s, out_path)
cat("OK\n")
"""


def persist_session(session: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Write the session as an RDS file the R bridge can read.

    Returns the session dict augmented with `_path` (RDS location) and
    `_metadata` (small dict for the LLM and the UI).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "session.json"
    rds_path  = out_dir / "session.rds"
    r_script  = out_dir / "_persist_session.R"

    payload = {k: v for k, v in session.items() if not k.startswith("_")}
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    r_script.write_text(R_PERSIST_SCRIPT, encoding="utf-8")

    proc = subprocess.run(
        ["Rscript", "--vanilla", str(r_script), str(json_path), str(rds_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not rds_path.exists():
        raise RuntimeError(
            "Failed to persist session as RDS.\n"
            f"  returncode: {proc.returncode}\n"
            f"  stdout:\n{proc.stdout}\n"
            f"  stderr:\n{proc.stderr}\n"
        )

    session["_path"] = str(rds_path)
    session["_metadata"] = {
        "n_int": session.get("n_int"),
        "n_ext": session.get("n_ext"),
        "p":     len(session.get("predictor_names", [])) or None,
        "predictor_names": session.get("predictor_names"),
        "has_internal_individual_data": "X_int" in session and "Y_int" in session,
        "has_internal_marginal_only":   "r_int" in session and "X_int" not in session,
        "has_external_theta":           "beta_ext" in session,
        "has_external_sigma2":          "Sigma_ext" in session,
        "has_reference_panel":          "Sigma_ref" in session,
    }
    return session
