<div align="center">

<img src="assets/banner.svg" alt="hyenovel — a discussion partner that helps you dissect a story's skeleton" width="100%">

<br>

![runs on Claude Code](https://img.shields.io/badge/runs%20on-Claude%20Code-d97757?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square)
![runtime](https://img.shields.io/badge/runtime-localhost%20only-6B7280?style=flat-square)

[繁體中文](README.md) · **English**

</div>

> A **critique & thinking tool** for literary short fiction, running on [Claude Code](https://claude.com/claude-code) — **on your subscription, not API tokens**.

## What it is · Who it's for

For people who **write literary short fiction in Chinese / Taiwanese (< 10k characters)**.

It isn't a paste-and-get-a-review one-shot. It's a **reading companion**: it reads your draft, talks it through with you, and visualizes the analysis — helping you read one piece to the bottom. When a story comes in, two **deliberately isolated** AIs work in the background: one only **observes** (extracting themes / motifs / techniques / effects / characters / beats, each pinned to verbatim quotes), the other is a **neutral reader** who writes down what it actually felt, where it got stuck, and what it thinks (prep notes, ranked by weight, no flattery). Observation and judgment stay apart — that's what keeps the judgment independent. The companion you talk to gets only the source and a condensed analysis — **never the notes** — and speaks from its own reading.

## A look at the interface

<!-- screenshots and demo to come -->

Dot-matrix type, soft blobs, one-key day/night. Three screens:

- **Entrance**: one sentence, one input box. Submit a draft or just start talking; recent works are listed below, and you can pick today's companion.
- **Work**: the draft on the left (paper, the reader's marks, version switching), three tabs on the right —
  - **Talk**: back-and-forth with the companion; whatever line it quotes gets underlined in the draft.
  - **Notes**: the neutral reader's prep notes, ranked by weight, each anchored to the source.
  - **Structure**: a dot-matrix intention chain (technique → effect → theme) and the text's tension.
- **Settings**: appearance, language, companions and data on their own page.

Narrow screens switch to a single pane; `⌘K` opens a command palette, with keyboard navigation throughout.

## Why it's different

| Dimension | hyenovel | A typical "paste into an AI" review |
|---|---|---|
| **Observe vs. judge** | two isolated subagents: observe first, judge second — judgment stays independent | one model writes it all at once; observation is polluted by judgment |
| **Citations** | every claim is **pinned to a verbatim quote**; a hard gate verifies it against the source and blocks hallucinated quotes | often riffs from impression, hard to trace back |
| **Billing** | runs on Claude Code, **on your subscription** — the whole pipeline isn't metered per token. At API price-list rates a single critique costs roughly **$0.7–0.9** (analyst + reviewer + deterministic layer); multi-turn discussion rides the cache and costs less. That delta is what the subscription saves versus per-token billing. | metered per API token; the more you talk, the more it costs |
| **Privacy** | **localhost, single-user** only; your story is processed through your own Claude Code subscription (Anthropic) — not uploaded to a separate third-party review service, not stored in a vendor database. Your writing stays in a local database | content uploaded to a third-party cloud review site |
| **Visualization** | intention chain (technique→effect→theme) + text tension; the draft is underlined wherever the companion quotes | plain bulleted text |
| **Interaction** | **talk** a piece through with the companion in three readings (direct / slow / imaginative) — doesn't just agree, doesn't rewrite for you, asks back | one-shot, tends toward flattering summaries |

## Install

**Prerequisites**

- [Claude Code](https://claude.com/claude-code) installed and signed in — this tool uses your subscription, not API billing.
- Python 3, Node.js.

**Steps**

```bash
git clone https://github.com/randyxu0711/hyenovel.git
cd hyenovel

# Backend (Python)
uv venv --python 3.14
uv pip install -r pyproject.toml

# Frontend (Node); dev.sh also auto-installs on first run
cd web && npm install && cd ..
```

## Run & use

### Dashboard (main entrance)

```bash
cd web && npm run build && cd ..   # first time, and after every pull
.venv/bin/python -m den.open       # ensures den is running, opens the browser
```

`den.open` exchanges a one-time launch code (valid for 120 s) and opens your default browser; if it can't (common on WSL), click the URL it prints. den serves the dashboard same-origin, with the API under `/api`.

For frontend development use `./dev.sh` instead (ensures den is running + starts vite at http://localhost:5173; Ctrl+C stops only the frontend).

Existing users: import pieces from the old `stories/` once with `python -m marrow.importer`.

> localhost, single-user only; subscription auth is bound to local credentials — **do not deploy to the cloud**.

### In the agent (a Claude Code session in any directory; register the hyenovel MCP first, see CLAUDE.md)

1. `/hyenovel:companion` — give a .md/.txt path to submit (analysis runs in the background); the companion speaks first, then you talk.
2. `/hyenovel:continue` — pick up the most recent piece. Finding works, reading the analysis or stopping a run: just ask ("which pieces do I have", "show me the analysis of the sea one").
3. `python -m export <slug>` — export a shareable `<slug>.md` and `<slug>.html` (intention chain + text-axis anatomy).

## How it works

```
submit_work(file path)  ─▶ den ─ analyst ▶ reviewer ─▶ DB (source of truth: observation + judgment)
                                                         │
                    ┌───────────────────┬────────────────┴────────────────┐
                    ▼                   ▼                                 ▼
          web (reads den /api)   talk_to_companion (MCP)        python -m export ─▶ md + html
```

The observer and the judge are **two independent steps with separate contexts** — never the same context — so judgment independence isn't polluted. The companion can start talking as soon as the analysis is ready, without waiting for the notes. Their outputs feed the visualization, drawing out the technique → effect → theme intention chain and the text tension curve. **Every claim must match the source verbatim** (a hard gate that blocks hallucinated quotes).

> For the internal contracts and design: `schemas/analysis.schema.json`, `docs/DESIGN.md`.

---

<div align="center">
<img src="assets/footer.svg" alt="hyenovel" width="100%">
</div>
