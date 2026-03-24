# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**KS Math Tutor** — an adaptive AI tutoring system that teaches one university-level mathematical concept at a time (initially real analysis). The system diagnoses the student, plans a personalised lesson, delivers it on a live whiteboard, handles interruptions, and evaluates understanding.

Design documents:

- [AIMathTutor.md](AIMathTutor.md) — Full system architecture, module specs, API contracts, MVP plan
- [Diagnosis.md](Diagnosis.md) — ML training blueprint for the Student Diagnosis Module

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, FastAPI, LangChain, LangGraph |
| LLM | Groq (default), Anthropic Claude, or OpenAI — set via `DEFAULT_LLM_PROVIDER` |
| Database | PostgreSQL (Fly.io managed) — persistent sessions, events, analytics |
| Session cache | Redis (Fly.io) — live session state during active tutoring |
| Frontend | Vanilla JS, HTML, CSS + KaTeX (math rendering via CDN) |
| Backend hosting | Fly.io (`backend/fly.toml`) |
| Frontend hosting | Vercel (`frontend/vercel.json`) |

## Project Structure

```text
KSProject/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, CORS, route registration
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic settings (reads .env)
│   │   │   └── llm.py                 # LLM factory: get_llm("fast"|"rich")
│   │   ├── db/database.py             # SQLAlchemy async engine + Base
│   │   ├── models/
│   │   │   ├── schemas.py             # Pydantic request/response models + enums
│   │   │   └── tables.py              # SQLAlchemy ORM tables
│   │   ├── session/manager.py         # Redis-backed session state (get/save/update)
│   │   ├── modules/
│   │   │   ├── input_understanding/handler.py   # LLM → structured target JSON
│   │   │   ├── diagnosis/
│   │   │   │   ├── handler.py         # LLM/ML diagnosis + question bank loader
│   │   │   │   ├── ml.py              # ML model loading & inference
│   │   │   │   ├── background.py      # Background materialization worker
│   │   │   │   └── taxonomy.py        # Question canonicalization
│   │   │   ├── lesson_planner/handler.py        # LLM lesson plan generation
│   │   │   ├── tutoring_delivery/
│   │   │   │   ├── graph.py           # LangGraph state machine (core orchestrator)
│   │   │   │   ├── delivery.py        # Section/interruption package generation
│   │   │   │   └── speech.py          # TTS integration (AWS Polly or mock)
│   │   │   ├── interruption/handler.py          # Registers interruptions in session state
│   │   │   └── evaluation/handler.py            # Scores post-lesson answers
│   │   └── api/routes/
│   │       ├── session.py             # /api/session/* endpoints
│   │       └── diagnosis.py           # /api/diagnosis/* endpoints
│   ├── alembic/                       # DB migration scripts
│   ├── data/
│   │   ├── question_banks/            # JSON question banks per subject area
│   │   ├── diagnosis_taxonomy/        # Topic metadata & misconception probes
│   │   └── models/                    # Trained ML model files (.pkl)
│   ├── scripts/                       # Standalone utilities (worker, training, export)
│   ├── tests/                         # pytest test suite
│   ├── Dockerfile
│   ├── fly.toml
│   └── requirements.txt
├── frontend/
│   ├── index.html                     # Single-page app
│   ├── src/css/main.css
│   └── src/js/
│       ├── api.js                     # Fetch wrapper for all backend calls
│       ├── whiteboard.js              # KaTeX section rendering + audio sync
│       ├── session.js                 # Client-side session state
│       └── app.js                     # Main UI controller / flow orchestration
├── .env.example
├── AIMathTutor.md
├── Diagnosis.md
└── CLAUDE.md
```

## Running Locally

**Backend:**

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env   # fill in keys
alembic upgrade head      # run DB migrations (requires DATABASE_URL)
uvicorn app.main:app --reload --port 8003
```

Requires a running PostgreSQL and Redis (or use cloud instances and point `.env` at them).

**Diagnosis background worker** (optional, run alongside API):

```bash
cd backend
python scripts/run_diagnosis_worker.py
```

Canonicalises generated unknown-topic diagnosis batches and materialises them into training records.

**Frontend:**
Open `frontend/index.html` directly in a browser, or serve with any static file server.
`window.API_BASE` in `api.js` defaults to `http://<current-page-hostname>:8003`. Override via `window.API_BASE` before the scripts load if using a different port.

**Run tests:**

```bash
# Backend (no pytest.ini — run directly)
cd backend
python -m pytest tests/ -v
python -m pytest tests/test_diagnosis_pipeline.py -v   # single file

# Frontend
cd frontend
npm test    # runs: node --test tests/whiteboard.test.js
```

**Deploy backend to Fly.io:**

```bash
cd backend
fly launch        # first time
fly secrets set ANTHROPIC_API_KEY=... DATABASE_URL=... REDIS_URL=... FRONTEND_ORIGINS=... FRONTEND_URL=...
fly deploy
```

Use `FRONTEND_ORIGINS` (comma-separated) as the primary CORS setting. `FRONTEND_URL` is kept as a legacy fallback.

**Deploy frontend to Vercel:**

```bash
cd frontend
vercel
```

## Architecture — LangGraph State Machine

The tutoring session is a LangGraph `StateGraph` compiled in [backend/app/modules/tutoring_delivery/graph.py](backend/app/modules/tutoring_delivery/graph.py):

```text
plan_lesson → teach_section ──→ evaluate → END
                   ↕
           handle_interruption
```

- State is checkpointed per `session_id` using `MemorySaver`.
- Compiled with `interrupt_after=["teach_section", "handle_interruption"]` so each step pauses and the API resumes it on the next `/advance` call.
- `route_after_teaching` decides: interruption pending → `handle_interruption`, all sections done → `evaluate`, else loop back to `teach_section`.
- Each node imports its handler lazily to avoid circular imports.
- `TutoringState` (TypedDict) carries: session metadata, lesson_plan, current_section_index, delivery_package, interruption_text, evaluation_questions, board_events.

## Session Flow (API)

```text
POST /api/session/create          → understand input, cache session state in Redis (phase: diagnosing)
GET  /api/diagnosis/:id/questions → load questions from question bank (or generate via LLM)
POST /api/diagnosis/submit        → run diagnosis, update Redis state (phase: planning)
POST /api/session/:id/advance     → drive LangGraph one step, returns AdvanceResponse
     phase=planning → seeds graph, runs plan_lesson + teach_section[0], pauses
     phase=teaching → resumes graph, delivers next section, pauses
     phase=interrupted → injects interruption via update_state(), resumes
     phase=done → AdvanceResponse includes evaluation_questions
POST /api/session/:id/interrupt   → mark interruption_pending in Redis
POST /api/session/evaluate        → score final answers, update phase: done
GET  /api/session/:id/state       → read current Redis session state
```

`AdvanceResponse` shape: `{phase, section, content, board_events, delivery_package, lesson_sections, evaluation_questions}`

## Key Design Decisions

- **Redis** is the source of truth for live phase tracking (4-hour TTL). PostgreSQL stores the durable audit trail (sessions, lesson events, evaluation results).
- **LangGraph graph** is the single authoritative tutoring orchestrator — all section delivery, interruptions, and evaluation flow through it.
- **LLM factory** (`core/llm.py`): call `get_llm("fast")` or `get_llm("rich")`. Fast tier uses smaller/cheaper models (llama-3.1-8b / claude-haiku / gpt-4o-mini); rich tier uses larger models (llama-3.3-70b / claude-sonnet-4-6 / gpt-4o). Provider selected by `DEFAULT_LLM_PROVIDER` env var.
- **Whiteboard** renders KaTeX from `$...$` / `$$...$$` in LLM output automatically via CDN auto-render — no pre-processing needed.
- **Question banks** live in `backend/data/question_banks/<subject_area>.json`. Topic-specific questions are keyed by snake_case topic name; falls back to `general_questions`.
- **Delivery packages** are the unit of section content: each has typed `steps` (heading/text/math/highlight/pause), `spoken_text` for TTS, and a `resume_cursor` checkpoint.
- **TTS**: set `TTS_PROVIDER=polly` (AWS Polly) or `TTS_PROVIDER=mock` for local dev without audio.

## Diagnosis Module

**Diagnosis modes** (set via `DIAGNOSIS_MODE` env var):

- `llm` — LLM-only diagnosis (default MVP)
- `ml_shadow` — Run ML models in parallel with LLM for validation/comparison
- `ml_primary` — Use ML models directly when confidence ≥ `DIAGNOSIS_ML_PRIMARY_MIN_CONFIDENCE` (default 0.62)

Four supervised learning tasks (see [Diagnosis.md](Diagnosis.md) for full label schemas):

- **Task A**: Learner level — 4-class (`beginner`, `beginner_intermediate`, `intermediate`, `advanced`)
- **Task B**: Prerequisite gap detection — multi-label
- **Task C**: Misconception classification — multi-label
- **Task D**: Teaching strategy — single-label (`intuition_first`, `example_first`, `formal_definition_first`, `proof_first`, `prerequisite_micro_lesson_first`)

**ML training scripts** (all in `backend/scripts/`):

```bash
python scripts/generate_synthetic_diagnosis_dataset.py
python scripts/train_diagnosis_baseline.py
python scripts/evaluate_diagnosis_models.py
python scripts/export_diagnosis_dataset.py   # exports DB records to JSONL
```

ML models are plugged into `diagnosis/handler.py` — swapping LLM → ML doesn't touch any other module.
