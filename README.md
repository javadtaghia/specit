# SPECiT (`Si`) — Architecture & Specification Studio *(Beta)*

**SPECiT** (`v0.1.0-beta`) is a local-first, source-grounded, human-reviewed architecture studio that transforms project specifications into structured process catalogues (`{PREFIX}-CA-001`), editable MS Word-style work flows (`{PREFIX}-WF-001`), hand-drawn interactive diagrams (`.drawio`-compatible), adversarial quality assessments, and SC (`{PREFIX}-SC-001`) handoffs.

> Demo walkthrough: [`demo/vending-machine-demo.mp4`](demo/vending-machine-demo.mp4)

## Key Capabilities

- **Use Your Existing AI Subscriptions** (no extra API keys needed): auto-detects local authenticated **GitHub Copilot (`copilot`)**, **Claude (`claude`)**, **OpenAI Codex (`codex`)**, and **Google Gemini (`gemini`)** CLIs with live configured model discovery — plus optional direct API keys (OpenAI, Anthropic, Google Gemini, GitHub Models).
- **6-Step Guided Wizard**:
  1. **Upload** — Table-preserving DOCX, PDF (`pdfplumber`), Markdown, and TXT ingestion with configurable project prefix (`PRJ-CA-001`, `PRJ-WF-001`, `PRJ-SC-001`).
  2. **Catalogue** — Structured process & rule editor (`source_defined` / `design_proposed` / `unresolved`) with citation verification and human approval gates.
  3. **Work Flows** — Full-viewport **🗺️ Flows Map**, directly editable **📄 Word View** (eye-friendly Inter typography + warm paper + drag/drop & `Cmd+V` image insertion), **✏️ Split Edit**, and a **100% built-in hand-drawn interactive Diagram Editor** (`.drawio` XML compatible, inline & full-screen canvas).
  4. **Quality** — Deterministic citation/diagram checks, per-process **Batch Deep QA**, **Batch Revise with Feedback**, **Batch Generate Missing**, side-by-side Artifact vs Source comparison, and GitHub-style color-coded Revision Diffs.
  5. **Foundation** — Constitution, Functional Specification, and Clarification & Open Decisions Register.
  6. **SC** — Technical Plan, Ordered Tasks (`{PREFIX}-SC-001`), MS Word (`.docx`) export (with embedded images), portable `{PREFIX}-SPECIT-YYYYMMDD-HHMMSS.zip` bundles, and reviewed vertical code slice proposals.
- **Scoped Review Comments & AI Rerun** — Comment on any catalogue process, highlighted text passage, or document; run focused **🤖 Review by AI** or **⚡ Rerun This Scope** with open comments.
- **Per-Project Git Sync & Portable `.zip` Bundles** — Connect any project workspace to a Git remote (commit locally, push, pull) or export/open the entire project as a portable `.zip` archive.

## Desktop Releases (Windows `.exe` & macOS `.dmg`)

Download pre-built desktop packages from **GitHub Releases**:
- **macOS**: `SPECiT-<version>-macOS-arm64.dmg` — drag **SPECiT.app** to **Applications** and open.
  - *Note for unsigned Beta releases on macOS*: Because this beta build is ad-hoc signed (not yet Apple-notarized), macOS Gatekeeper may block the first launch. After trying to open **SPECiT.app**, open **System Settings → Privacy & Security**, scroll to **Security**, and click **Open Anyway** next to SPECiT. Startup logs are written to `~/Documents/SPECiT/specit.log`.
- **Windows**: `SPECiT-<version>-Windows-x64.exe` — double-click to launch SPECiT locally in your browser.

When launched as a desktop app, SPECiT stores project workspaces in `~/Documents/SPECiT/workspace` (overridable via `SPECIT_WORKSPACE`) and shows a compact desktop status window to reopen the browser, open the workspace folder, or quit cleanly.

### Build Locally

```bash
# Install packaging tools
pip install -r requirements.txt pyinstaller pillow

# macOS (.app + .dmg)
./packaging/build_mac_dmg.sh

# Windows (PowerShell, standalone .exe)
./packaging/build_win_exe.ps1
```

### Automated GitHub Releases

Pushing a version tag (e.g. `git tag v0.1.0-beta && git push origin v0.1.0-beta`) triggers [`.github/workflows/release.yml`](.github/workflows/release.yml), which runs all unit tests, builds both **macOS `.dmg`** and **Windows `.exe`**, and attaches them to a GitHub Release (automatically marked as a pre-release for `-beta` tags).

## Quick Start (From Source)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8501** in your browser. Click the AI provider logo (or **⚙**) in the top-right bar to choose your subscription CLI or API key.

## Project Structure

```text
specit/
  app.py                  # FastAPI backend + serves SPECiT studio on port 8501
  web/
    index.html            # 6-step wizard, Open Canvas, Word Studio, Comments & Git modals
    styles.css            # Inter typography, warm paper & Toyota Red accent theme
    diagram-editor.js     # Built-in hand-drawn SVG diagram editor (.drawio XML compatible)
    app.js                # Studio state, direct Word editing, batch runs, context menu, diffs
  engine/
    sources.py            # Table-aware PDF/DOCX/MD/TXT parser + citation indexer
    model.py              # Typed Pydantic schemas
    llm.py                # Subscription CLI (Copilot/Claude/Codex/Gemini) & API client
    diagrams.py           # Mermaid (LR/TB, subgraphs, class, state) -> .drawio XML converter
    pipeline.py           # Multi-chunk extraction, artifact generation, QA, scoped review/rerun
    storage.py            # Versioned workspaces, unified diffs, assets, approval cascade
    git_sync.py           # Per-project local Git init, browsable docs/ sync, commit/push/pull
    export.py             # MS Word (.docx), Spec Kit ZIP, portable project ZIP, safe code save
  prompts/                # Domain-agnostic stage prompts
  examples/               # Sample specifications (CLEP OCD PDF, Smart Vending Machine MD)
  scripts/                # Demo video recorder
  demo/                   # Recorded HD walkthrough video
  tests/                  # Unit & API tests
```

## Run Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## License

Licensed under the [MIT License](LICENSE).
