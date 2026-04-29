# mainger-agent — Complete Tutorial

This document walks you through installing and using **mainger-agent**, an
LLM-driven assistant for the `mainger` framework for privacy-constrained
transfer learning.

The tool comes in two interchangeable forms:

- A **command-line tool** (`agent.py`) — single-shot analysis from a terminal.
- A **web UI** (`server.py` + `web/index.html`) — multi-turn chat in your browser.

Both share the same R bridge to the `mainger` package, the same vendor support,
and the same output format. The only difference is the interface.

## Table of contents

1. [What you'll need](#1-what-youll-need)
2. [Install](#2-install)
3. [Get an API key](#3-get-an-api-key)
4. [Configure](#4-configure)
5. [Use the command-line tool](#5-use-the-command-line-tool)
6. [Use the web UI](#6-use-the-web-ui)
7. [Output files](#7-output-files)
8. [Choosing a model](#8-choosing-a-model)
9. [Troubleshooting](#9-troubleshooting)
10. [Privacy and security](#10-privacy-and-security)

---

## 1. What you'll need

### Software (all platforms)

| Tool   | Minimum version | What it's for                           |
|--------|-----------------|-----------------------------------------|
| Python | 3.10+           | The agent orchestration code            |
| R      | 4.2+            | The `mainger` package and the bridge    |
| `mainger` R package | 0.2.0+ | The actual statistical computation |
| `jsonlite` R package | any | JSON I/O between Python and R        |
| An LLM API key | — | At least one (see Section 3)           |

### Verify what's already installed

Open a terminal and run:

```bash
python --version          # should print 3.10 or higher
Rscript --version         # should print 4.2 or higher
```

- **macOS / Linux**: open Terminal.
- **Windows**: open PowerShell (or Command Prompt). If `Rscript` isn't found,
  add R's `bin` folder (typically `C:\Program Files\R\R-x.y.z\bin\`) to your
  `PATH` and restart the shell.

If Python is missing, install from [python.org](https://www.python.org/downloads/)
or via `brew install python` / `apt install python3` / `dnf install python3`.

If R is missing, install from [r-project.org](https://cran.r-project.org/) for
any platform, or `brew install r` on macOS.

---

## 2. Install

### 2.1 Get the code

Clone the repository (or download and unzip it):

```bash
git clone https://github.com/<your-org>/mainger-agent.git
cd mainger-agent
```

On Windows, paths with spaces or parentheses must be quoted:

```powershell
cd "C:\path\with spaces\mainger-agent"
```

### 2.2 Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs the Anthropic, OpenAI, and Google GenAI SDKs plus FastAPI,
Uvicorn, pandas, jinja2, pyyaml, python-dotenv, and python-multipart.
Should finish in under a minute.

> **Recommended**: use a virtual environment to keep these dependencies isolated:
> ```bash
> python -m venv .venv
> source .venv/bin/activate          # macOS/Linux
> .venv\Scripts\activate             # Windows PowerShell
> pip install -r requirements.txt
> ```

### 2.3 Install the `mainger` R package

You need the `mainger` package (v0.2.0 or higher) plus `jsonlite`.

```bash
Rscript -e "install.packages('jsonlite', repos='https://cloud.r-project.org')"
Rscript -e "install.packages('path/to/mainger_0.2.0.tar.gz', repos=NULL, type='source')"
```

Replace `path/to/mainger_0.2.0.tar.gz` with the actual location of the
tarball on your machine. On Windows, forward slashes are fine inside R
strings:

```powershell
Rscript -e "install.packages('C:/Downloads/mainger_0.2.0.tar.gz', repos=NULL, type='source')"
```

### 2.4 Verify everything

Run these three sanity checks:

```bash
# 1) Python deps imported cleanly
python -c "from agent import run_agent; print('agent OK')"

# 2) mainger is the right version
Rscript -e "library(mainger); cat('mainger', as.character(packageVersion('mainger')), '\n')"

# 3) The R bridge can read a tiny JSON file
echo '{"hello":"world"}' > test.json
Rscript --vanilla -e "x <- jsonlite::fromJSON('test.json'); cat(x$hello, '\n')"
rm test.json
```

You should see `agent OK`, `mainger 0.2.0` (or higher), and `world`. If any
of these fails, fix that one before proceeding.

---

## 3. Get an API key

You need an API key from at least one provider. Pick whichever is easiest
to sign up for. The tool supports nine vendor categories grouped into three
families.

### 3.1 Closed-source hosted models

These vendors run their own proprietary models through their own APIs. Each
requires a separate signup and (usually) a credit card.

#### Anthropic — Claude family

1. Sign up at <https://console.anthropic.com>.
2. Add a payment method under **Plans & Billing** (Anthropic doesn't offer a
   meaningful free tier; expect to add a credit card to do real work).
3. Navigate to **API Keys** in your account settings.
4. Click **Create Key**, give it a descriptive name, and copy the value
   (starts with `sk-ant-`). You won't see the full key again.

**Models** (pick in the UI or set in `config.yaml`):
- `claude-opus-4-7` — strongest, best for paper-quality runs
- `claude-sonnet-4-6` — balanced
- `claude-haiku-4-5-20251001` — cheap and fast

**Env var**: `ANTHROPIC_API_KEY`.

#### OpenAI — GPT family

1. Sign up at <https://platform.openai.com>.
2. Add a payment method under **Settings → Billing**. OpenAI requires
   prepaid credits before any API calls go through.
3. Go to **API Keys** in the left sidebar.
4. Click **Create new secret key**, copy the value (starts with `sk-`).
   You won't see it again.

**Models**:
- `gpt-4o` — strongest in this family
- `gpt-4o-mini` — much cheaper, but its output can be less reliable for
  long structured JSON. Fine for development; switch to `gpt-4o` for final
  runs.

**Env var**: `OPENAI_API_KEY`.

#### Google — Gemini family

The signup path here has the lowest friction of the closed providers.

1. Visit <https://aistudio.google.com/app/apikey> and sign in with a Google
   account.
2. Click **Create API key**. If you don't already have a Google Cloud project,
   AI Studio creates one automatically.
3. Copy the key (begins with `AIza...`).

Free tier exists for development; pricing applies once you exceed quotas.

**Models**:
- `gemini-2.5-pro` — strongest reasoning
- `gemini-2.5-flash` — balanced, fast
- `gemini-1.5-pro` — older but still useful

**Env var**: `GOOGLE_API_KEY` (or `GEMINI_API_KEY` — both are accepted; if
both are set, `GOOGLE_API_KEY` wins).

#### xAI — Grok family

1. Sign up at <https://console.x.ai>.
2. Add a payment method.
3. Go to **API Keys** and click **Create API Key**.

**Models**:
- `grok-4`, `grok-3`, `grok-3-mini`

**Env var**: `XAI_API_KEY`.

### 3.2 Open-source models via inference providers

These vendors **host** open-source models (Qwen, Llama, Mixtral, DeepSeek,
etc.) so you don't need a GPU. You bring an API key just like for closed
models, but you pay much less per token.

#### OpenRouter — recommended starter

OpenRouter is the easiest path to trying open-source models. One key works
across many providers, and a few models are available on a free tier.

1. Sign up at <https://openrouter.ai/keys>. GitHub or Google sign-in works.
2. Click **Create Key**, copy the value (starts with `sk-or-`).
3. (Optional) Add credits in **Settings → Credits** for paid models.

**Models**:
- `qwen/qwen-2.5-72b-instruct`
- `meta-llama/llama-3.3-70b-instruct`
- `deepseek/deepseek-chat`
- `google/gemini-flash-1.5` (Gemini through OpenRouter — sometimes useful
  if you want one billing relationship)

Browse [openrouter.ai/models](https://openrouter.ai/models) for the full list.

**Env var**: `OPENROUTER_API_KEY`.

#### Together AI

Solid commercial provider with broad model support and reasonable prices.

1. Sign up at <https://api.together.xyz>. Email or Google sign-in.
2. Click your avatar → **API Keys** → **Create API Key**.
3. Copy the value.

**Models** (the `-Turbo` suffix is Together's optimized variant):
- `Qwen/Qwen2.5-72B-Instruct-Turbo`
- `Qwen/Qwen2.5-7B-Instruct-Turbo`
- `meta-llama/Llama-3.3-70B-Instruct-Turbo`
- `mistralai/Mixtral-8x7B-Instruct-v0.1`

**Env var**: `TOGETHER_API_KEY`.

#### Fireworks AI

Similar to Together. Very fast inference, broad model support.

1. Sign up at <https://fireworks.ai>.
2. Go to your account dashboard, click **API Keys**, create one.
3. Copy the value.

**Models** (note the `accounts/fireworks/models/...` prefix):
- `accounts/fireworks/models/qwen2p5-72b-instruct`
- `accounts/fireworks/models/llama-v3p3-70b-instruct`
- `accounts/fireworks/models/mixtral-8x22b-instruct`

**Env var**: `FIREWORKS_API_KEY`.

#### Groq

Specialty: extremely fast inference (custom hardware). Has a usable free tier.

1. Sign up at <https://console.groq.com>.
2. Go to **API Keys** → **Create API Key**.
3. Copy the value.

**Models**:
- `llama-3.3-70b-versatile`
- `qwen-2.5-32b`
- `mixtral-8x7b-32768`

**Env var**: `GROQ_API_KEY`.

#### HuggingFace — Inference Providers

HuggingFace's inference router gives you a single endpoint that proxies
across many partner providers. **Important**: you must create a
**fine-grained token** with the "Make calls to Inference Providers"
permission, or the request will fail with a 401 error.

1. Sign up at <https://huggingface.co>.
2. Go to **Settings → Access Tokens** (<https://huggingface.co/settings/tokens>).
3. Click **Create new token**.
4. Choose **Fine-grained**.
5. Give it a name (e.g., `mainger-agent`).
6. Under permissions, **enable "Make calls to Inference Providers"**.
   Without this, requests will return 401 even though the token "exists".
7. Click **Create token**, copy the value (starts with `hf_`).

**Models** are HuggingFace model IDs:
- `Qwen/Qwen2.5-7B-Instruct`
- `Qwen/Qwen2.5-72B-Instruct`
- `meta-llama/Llama-3.3-70B-Instruct`
- `deepseek-ai/DeepSeek-V3`

**Optional model suffixes** (HuggingFace-specific):
- `Qwen/Qwen2.5-72B-Instruct:fastest` — pick the fastest provider
- `Qwen/Qwen2.5-72B-Instruct:cheapest` — pick the cheapest provider
- `Qwen/Qwen2.5-72B-Instruct:together` — pin to a specific underlying provider

If a model isn't available on any partner, requests will fail; the
HuggingFace model page lists which providers serve each model.

**Env var**: `HUGGINGFACE_API_KEY` or `HF_TOKEN`. Free tier includes monthly
inference credits; HuggingFace Pro adds more.

#### Custom — your own OpenAI-compatible endpoint

Pick this if you've deployed your own model server (vLLM, Ollama, TGI,
HuggingFace Inference Endpoints, or anything else exposing an OpenAI-
compatible chat completions API).

You'll need:
- A **base URL** ending in `/v1` (e.g., `http://localhost:8000/v1`).
- A model name accepted by your server.
- An API key (often anything; e.g., Ollama accepts `ollama` literally).

**This is what you'll point at your fine-tuned `mainger-qwen` model** once
training finishes. No code changes required — you just pick "Custom" in
the vendor dropdown, paste the URL, and type the model name.

### 3.3 Quick comparison

| Provider     | Models                       | Free tier  | Tool-use reliability  | Best for                       |
|--------------|------------------------------|------------|------------------------|--------------------------------|
| Anthropic    | Claude Opus / Sonnet / Haiku | No         | Excellent              | Final/paper-quality runs        |
| OpenAI       | GPT-4o / -4o-mini            | No         | Excellent              | Default closed model            |
| Google       | Gemini 2.5 Pro / Flash       | Yes        | Good                   | Cost-sensitive closed model     |
| xAI          | Grok 4 / 3 / 3-mini          | Limited    | Good                   | Long-context tasks              |
| OpenRouter   | Qwen, Llama, DeepSeek, etc.  | Some models| Variable by model      | Trying many open-source models  |
| Together     | Qwen, Llama, Mixtral         | Free credits | Good                 | Cheap reliable open-source      |
| Fireworks    | Qwen, Llama, Mixtral         | Free credits | Good                 | Fast open-source                |
| Groq         | Llama, Qwen, Mixtral         | Generous   | Smaller models can hallucinate | Speed                  |
| HuggingFace  | Most open models             | Yes (limited) | Variable by underlying provider | Multi-provider routing |
| Custom       | Whatever you serve           | N/A        | Depends on model       | Self-hosted or fine-tuned       |

If you have no API key yet and want to test the tool right now, **OpenRouter
is the lowest-friction option** — sign up, grab a key, and use one of their
free-tier models.

---

## 4. Configure

### 4.1 Set up `.env` (your API keys)

Copy the example file and edit it:

```bash
cp .env.example .env                # macOS/Linux
copy .env.example .env              # Windows
```

Open `.env` in any text editor and uncomment the line for your chosen vendor.
You can fill in multiple — only the one matching your selected vendor will
be used. **No quotes around the value**.

```
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
XAI_API_KEY=xai-...
OPENROUTER_API_KEY=sk-or-v1-...
TOGETHER_API_KEY=...
FIREWORKS_API_KEY=...
GROQ_API_KEY=...
HUGGINGFACE_API_KEY=hf_...
```

`.env` is in `.gitignore` by default — never commit it to version control.

### 4.2 Set up `config.yaml` (default vendor and model)

Open `config.yaml` and pick one vendor + model that matches your `.env`:

```yaml
vendor: anthropic
model: claude-opus-4-7
max_tokens: 4096
temperature: 0.0          # keep low for reproducibility
max_tool_iterations: 8    # safety stop for the agent loop
```

Vendor names accepted: `anthropic`, `openai`, `gemini`, `xai`, `together`,
`fireworks`, `openrouter`, `groq`, `huggingface`, `custom`.

You can override these per-run (CLI flags or web UI dropdowns), so the
config.yaml values are just the defaults.

---

## 5. Use the command-line tool

### 5.1 Basic invocation

The repository includes a small synthetic example. Run the agent on it:

**macOS / Linux**:
```bash
python agent.py \
    --input examples/partial_example.csv \
    --external-coef examples/external_coef.csv \
    --regime partial \
    --out-dir runs/demo
```

**Windows PowerShell** (one line):
```powershell
python agent.py --input examples\partial_example.csv --external-coef examples\external_coef.csv --regime partial --out-dir runs\demo
```

You'll see four progress steps and then output paths printed. The whole run
takes 10–30 seconds depending on the model.

### 5.2 All command-line flags

| Flag | Required | Description |
|------|----------|-------------|
| `--input PATH`            | yes  | Internal individual-data file (CSV or Parquet). First column is the response Y; remaining columns are predictors. |
| `--external-coef PATH`    | yes  | External coefficients file (CSV or Parquet). Two columns: `variable, estimate`. |
| `--external-sigma PATH`   | no   | External Σ₂ matrix; required only for the **full** regime. |
| `--reference-sigma PATH`  | no   | Reference Σ panel; required only for the **restricted** regime. |
| `--sigma2-int FLOAT`      | no   | Internal error variance estimate. |
| `--sigma2-ext FLOAT`      | no   | External error variance estimate. |
| `--n-ext INT`             | no   | External sample size. Used in concordance and full-regime bound. |
| `--regime {full,partial,restricted}` | no | Optional hint; the agent calls `detect_regime` regardless and uses what it finds. |
| `--vendor NAME`           | no   | Override `config.yaml` vendor for this run. |
| `--model NAME`            | no   | Override `config.yaml` model for this run. |
| `--base-url URL`          | no   | Custom OpenAI-compatible endpoint URL (required for `vendor=custom`). |
| `--config FILE`           | no   | Use a different config file (default: `config.yaml`). |
| `--out-dir DIR`           | no   | Where to write outputs (default: `runs/latest`). |
| `--message TEXT`          | no   | Override the default user message. |

### 5.3 Examples

**Full regime** (need external Σ₂):
```bash
python agent.py \
    --input my_data/internal.csv \
    --external-coef my_data/external_coefs.csv \
    --external-sigma my_data/external_sigma.csv \
    --sigma2-ext 0.85 --n-ext 8000 \
    --regime full \
    --out-dir runs/full_run
```

**Restricted regime**:
```bash
python agent.py \
    --input my_data/marginal_only.csv \
    --external-coef my_data/external_coefs.csv \
    --reference-sigma my_data/reference_panel.csv \
    --regime restricted \
    --out-dir runs/restricted_run
```

**Try a different vendor without editing config.yaml**:
```bash
python agent.py \
    --vendor openrouter \
    --model qwen/qwen-2.5-72b-instruct \
    --input examples/partial_example.csv \
    --external-coef examples/external_coef.csv \
    --regime partial \
    --out-dir runs/qwen_test
```

**Use a custom OpenAI-compatible endpoint** (e.g., your own vLLM server):
```bash
python agent.py \
    --vendor custom \
    --base-url http://localhost:8000/v1 \
    --model my-finetuned-mainger-qwen \
    --input examples/partial_example.csv \
    --external-coef examples/external_coef.csv \
    --regime partial \
    --out-dir runs/local_test
```

---

## 6. Use the web UI

The web UI is the better experience for **interactive analysis** — multi-turn
conversation, follow-up questions, and the ability to update parameters
mid-session.

### 6.1 Starting the server

From the project root:

```bash
python server.py
```

You should see:

```
============================================================
  mainger-agent web UI (multi-vendor)
============================================================
  open: http://localhost:8000
  stop: Ctrl+C
============================================================
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Open <http://localhost:8000> in any browser. The server runs locally on
your own machine — nothing is hosted externally.

### 6.2 First analysis: the setup form

When you open the page, you'll see a setup form with five sections:

1. **Required inputs**: internal data file and external coefficients file.
2. **Optional — regime-specific**: external Σ₂ (full regime) or reference Σ (restricted).
3. **Optional — hints & parameters**: regime hint, `n_ext`, `sigma2_int`, `sigma2_ext`.
4. **LLM**: vendor dropdown (closed and open-source families), model name (typeable + autocomplete), API key with show/hide toggle, optional Base URL for OpenAI-compatible vendors.
5. **Initial message**: default is "Please analyze my data and produce the integration report, code, and explanation."

The vendor dropdown is grouped:
- **Closed (hosted APIs)**: Anthropic, OpenAI, Google, xAI
- **Open-source (via inference providers)**: Together, Fireworks, OpenRouter, Groq, HuggingFace, Custom

Click **Start session** to run the first analysis.

### 6.3 Reading the chat thread

After the form submits, the UI flips into chat mode:

- A **session banner** at the top shows the current session metadata
  (`n_int`, `n_ext`, `p`, which fields are populated).
- A **message thread** below shows turns alternating between you (right-aligned
  bubbles) and the agent (left-aligned bubbles).
- The agent's bubble contains:
  - Any text response.
  - A **collapsible trace** showing every tool call and its result.
  - **Three artifact tabs**: Report (markdown), Code (R), Explanation (markdown).
  - **Download buttons** for each artifact.

Math notation in the markdown (e.g., `$\eta^\star$`) renders via KaTeX;
R code is syntax-highlighted.

### 6.4 Asking follow-up questions

Below the thread is a **composer** with a textarea and three action buttons:

- **⚙ (gear)** — toggles a small panel with `n_ext`, `sigma2_int`, `sigma2_ext`
  inputs you can update before sending. The gear icon shows a dot (⚙•) when
  any value is set.
- **📎 (paperclip)** — opens a file picker to attach files. Each attachment
  shows as a chip with a role dropdown (Internal data / External coefs /
  External Σ / Reference Σ).
- **Send** — sends the message and any attachments / parameter updates.

You can also press **Ctrl+Enter** (or **Cmd+Enter** on macOS) inside the
textarea to send.

**Examples of follow-up messages**:
- "Why did you pick that value of eta?" → agent answers in plain prose, no
  tools called.
- "Re-run with eta=0.05" → agent calls `fit_integrated_estimator` again
  and produces a new set of artifacts in a new bubble.
- "Switch to cv tuning" + open the gear panel and set `n_ext=20000` →
  agent updates the session and re-runs.

### 6.5 Updating data mid-session

Two ways to update data after the initial setup:

**Numeric parameters** (`n_ext`, `sigma2_int`, `sigma2_ext`) — click the ⚙
gear, enter values, type your message, click Send. The session metadata
updates and the agent runs the next turn with the new values.

**File replacements** — click 📎, pick a file, the chip appears with a role
dropdown set to "Internal data" by default. Click the dropdown to change
the role to "External coefs", "External Σ", or "Reference Σ". The
uploaded file replaces the corresponding session field, and the agent
runs with the updated session.

### 6.6 Switching vendors mid-experiment

The vendor and model are locked at session start. To switch, click
**New session** in the banner, which closes the current session and
returns to the setup form. Re-upload your files and pick the new vendor.

This is intentional — the message history is in vendor-specific format,
and switching mid-conversation can produce subtle errors.

### 6.7 Multi-user note

The web UI is designed for **single-user local use**. The server stores
session state in memory and accepts API keys via the form, which is fine
for `127.0.0.1` access. **Do not expose this server beyond localhost**
without first switching to a different authentication model — browser-
entered keys would become network-visible.

---

## 7. Output files

Every run — CLI or web — writes the same five files to a session directory
under `runs/`:

| File | What's in it |
|------|--------------|
| `report.md` | Final integration report (markdown) |
| `analysis.R` | Runnable R script reproducing the analysis |
| `explanation.md` | Plain-language summary of findings |
| `trace.json` | Every tool call the LLM made — full audit trail |
| `final.json` | LLM's raw final response before rendering |

Plus internal files: `session.rds` (the canonical session data, used by
the R bridge), `session.json` (intermediate JSON), `_persist_session.R`
(the R conversion script), and `chat_log.json` (web-UI sessions only).

You can verify the analysis externally by running the generated R script:

```bash
Rscript runs/<session-id>/analysis.R
```

The coefficients it prints should match those in `report.md`. If they
don't, the LLM hallucinated — check `trace.json` to see what really came
back from the tools.

---

## 8. Choosing a model

### For development

Use a cheap, fast model: `claude-haiku-4-5-20251001`, `gpt-4o-mini`,
`gemini-2.5-flash`, or any open-source model on Groq / OpenRouter free tier.
You'll iterate faster and pay less while you're debugging.

### For final / paper-quality runs

Use a strong model: `claude-opus-4-7`, `gpt-4o`, or `gemini-2.5-pro`. These
follow the structured-output format much more reliably, so you'll see fewer
parser failures and more consistent artifacts.

### Cost considerations

Rough order of magnitude per million tokens (verify current pricing at the
provider's site — these numbers move):

- Cheapest: Groq free tier, OpenRouter free models, Gemini Flash (~free to a few cents)
- Mid: GPT-4o-mini, Claude Haiku, hosted Qwen/Llama (~10–30 cents)
- High: GPT-4o, Claude Sonnet (~$3–5)
- Highest: Claude Opus, Gemini 2.5 Pro (~$15)

A typical run is 5,000–20,000 tokens, so even Claude Opus is well under
$0.50 per analysis. Budget $5–10 to comfortably get through development and
a paper's worth of figures.

### Tool-use compliance is the key quality marker

Every model will eventually fail to produce all three artifacts in the
expected JSON format. Stronger models fail less often. If you're seeing
"the agent's output came back as raw text instead of artifact tabs", the
fix is usually switching to a stronger model rather than tweaking the
prompt.

---

## 9. Troubleshooting

### "ANTHROPIC_API_KEY not provided" (or equivalent for other vendors)

Your `.env` isn't being read, or the wrong key is set for the vendor in
`config.yaml`. Check that:
1. `.env` is in the project root (same folder as `agent.py`).
2. The line for your vendor is uncommented (no `#` at the start).
3. The vendor in `config.yaml` matches the env var you set.

### "Failed to persist session as RDS"

The R bridge couldn't convert your data. The error includes `stdout` and
`stderr` from R — read those carefully. Most common cause: a column that's
supposed to be numeric contains non-numeric values (empty strings, dates,
"N/A", etc.).

### "system is computationally singular" or singular matrix errors

Your internal sample size is too small relative to the number of predictors.
The `mainger` package needs `n_int` substantially larger than `p` for stable
OLS. Try removing collinear predictors, or use a larger sample.

### "LLM produced no tool calls and no parseable final JSON" / output appears as raw text instead of artifact tabs

The LLM emitted artifacts in a format the parser doesn't recognize. The
parser handles most reasonable formats (JSON blocks, multi-block JSON,
fenced R + markdown blocks), but smaller models occasionally find new ways
to fail. Two fixes:
1. **Switch to a stronger model** (most common solution).
2. Open `final.json` to see exactly what the LLM emitted; if it's
   structurally close to the expected format but with a quirk, send the
   contents and we can extend the parser.

### HuggingFace 401: "Invalid username or password"

Your token doesn't have the right permissions. HuggingFace tokens must be
created as **fine-grained** tokens with **"Make calls to Inference Providers"**
explicitly enabled. The default "Read" token is not enough. See Section 3.2
for the full procedure.

### Server starts but the page is blank / 404

The frontend isn't where the server expects it. Verify:
```
ls web/index.html        # macOS/Linux
dir web\index.html       # Windows
```

If the file isn't there, place it under `web/` in your project root and
restart the server.

### Encoding issues — Greek letters appear as `Î·` instead of `η`

This means a file is being read or written with the wrong encoding. The
current code specifies UTF-8 everywhere it can, but if you've edited
`skill.md` in an editor that defaulted to cp1252 / Windows Latin-1, the
file on disk will be wrong. Open `skill.md` in VS Code, check the bottom-
right status bar — it should say "UTF-8". If not, click that label and
re-save as UTF-8.

### "Hit max_tool_iterations without final answer"

The LLM is looping (calling tools repeatedly without producing the final
artifact bundle). Either bump `max_tool_iterations` in `config.yaml` to
something like 16, or switch to a stronger model. This usually only
happens with smaller open-source models.

### Tool-call quality is bad on a specific open-source model

Some smaller models (especially 7B variants) hallucinate tool arguments
or make up function names. Try a 70B+ model from the same provider, or
switch to OpenRouter and pick a known-good model like
`meta-llama/llama-3.3-70b-instruct`.

---

## 10. Privacy and security

### Data privacy

- **Your data stays on your machine.** The R bridge, session files, and
  artifacts are all local.
- **The LLM only sees session metadata** (sample sizes, dimensions,
  predictor names, regime classification) plus the messages you type.
  Raw individual-level data is **never sent to the LLM** — it stays in
  the R session and the R bridge does the actual computation.
- **Tool results returned to the LLM** are summary numbers (η values,
  coefficients, MSE estimates) — these do flow through the LLM, so
  treat the conversation log as having that level of disclosure.

### API key handling

- Keys in `.env` are read by the Python process and never logged.
- Keys typed in the browser API key field are sent over the local HTTP
  connection to your local server, used in-memory for one request, and
  dropped. They are never written to disk.
- The server binds to `127.0.0.1` only. Do not expose it beyond localhost
  without changing the auth model.

### What goes to the LLM provider

When you make a call through any vendor's API, the provider sees the
following in its server logs (per their privacy policy):
- Your API key (for billing/identification).
- The system prompt (your `skill.md` content + session metadata).
- Each user message you typed.
- Each tool result the agent fed back to the model.
- The model's responses.

Different vendors have different data-retention policies. Anthropic and
OpenAI offer enterprise tiers with zero retention; consumer tiers may
retain logs for 30 days for abuse monitoring. Read each vendor's API
data usage policy before sending sensitive data.

For maximally private analysis, use the **Custom** vendor pointing at a
**local** model server (vLLM, Ollama) — that way no data leaves your
machine at all. This is also what the local fine-tuned version of the
paper targets.

---

## Appendix: where to go from here

- **Edit `skill.md`** to tune the agent's tone or add domain-specific guidance.
- **Edit `templates/*.j2`** to adjust the format of the report, code, or
  explanation artifacts (these are referenced from the prompt as the
  expected structure).
- **Add a new tool** by adding an entry to `TOOL_SPECS` in `tools.py` and
  implementing it in `r_helpers/run_mainger.R`.
- **Add a new vendor** by adding a new client class in `llm_client.py`
  (necessary only for vendors with a non-OpenAI-compatible schema —
  anything OpenAI-compatible is already supported via the `Custom` vendor).
- **Deploy your own fine-tuned model** by uploading to HuggingFace, deploying
  as an Inference Endpoint, then pointing the `Custom` vendor at the endpoint
  URL.
