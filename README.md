# AI Math Tutor

**An adaptive AI-powered tutoring system that teaches university-level mathematics one concept at a time.**

> Submission for the [Education] pillar — AI Math Tutor democratises access to personalised, on-demand university mathematics tutoring for every student, anywhere.

---

## The Problem

University mathematics — real analysis, abstract algebra, advanced calculus — is where most students fall behind. Not because they lack ability, but because:

- Lectures move too fast for individual pacing
- Textbooks don't adapt to what the student already knows
- Private tutors are expensive and unavailable on demand
- Office hours are limited and rarely one-on-one

Students get stuck on a single concept for days with no personalised way forward. This disproportionately affects students without financial means or institutional support.

---

## The Solution

AI Math Tutor is a full-stack web application that replicates the experience of a private mathematics tutor — diagnosing the student, planning a personalised lesson, teaching it interactively, handling questions mid-lesson, and evaluating understanding — entirely on demand.

**Pillar: Education** | **Stage: Working MVP**

---

## How It Works — Student Journey

### Step 1 · Tell it what you want to learn
The student types a topic in natural language:
> *"Explain the epsilon-delta definition of a limit"*
> *"What is uniform continuity and why does it differ from pointwise continuity?"*
> *"Prove that every convergent sequence is Cauchy"*

The system uses an LLM to extract the precise topic, subject area, and likely prerequisites.

---

### Step 2 · Quick adaptive diagnostic
The system generates 4 targeted questions to assess:
- Knowledge of prerequisite concepts
- Common misconceptions for this specific topic
- Current comfort level (beginner → advanced)
- Preferred learning style

**Example questions for "epsilon-delta limit":**
1. *Can you describe what it means for a sequence to converge?*
2. *What does the symbol ∀ (for all) mean in a mathematical statement?*
3. *Have you encountered the concept of absolute value as a distance measure?*
4. *Would you prefer to start with the intuition, a worked example, or the formal definition?*

---

### Step 3 · Personalised lesson delivery
Based on the diagnosis, the system:
1. Assigns the student a **learner level** (beginner / beginner-intermediate / intermediate / advanced)
2. Detects **missing prerequisites** (e.g. absolute value, quantifiers)
3. Chooses a **teaching strategy**: intuition-first, example-first, formal-definition-first, proof-first, or prerequisite-micro-lesson-first
4. Generates a **lesson plan** with sections (e.g. Motivation → Intuition → Formal Definition → Worked Example → Common Mistakes)

The lesson is delivered **section by section** on a live interactive whiteboard:
- Mathematical notation renders in real-time using **KaTeX** ($\varepsilon$, $\delta$, $\forall$, $\exists$)
- Each section pauses so the student controls the pace
- A voice narration plays alongside (AWS Polly TTS)
- The chat panel shows the full lesson transcript

---

### Step 4 · Ask questions anytime
At any point during the lesson, the student can interrupt with a question:
> *"Wait — why does the order of the quantifiers matter?"*
> *"Can you give me a concrete numerical example?"*
> *"I don't understand why we need both δ and ε"*

The system answers the question **in the context of the current section**, then resumes the lesson from where it left off.

---

### Step 5 · Understanding check & evaluation
After all sections are delivered, the system generates 3 post-lesson questions:
1. **Explain-back** — restate the key idea in your own words
2. **Application** — apply the concept to a specific case
3. **Misconception probe** — identify a common wrong belief

The student's answers are scored by the LLM and a **personalised summary** is produced:
- Definition understanding: strong / moderate / weak
- Intuition understanding: strong / moderate / weak
- Application ability: strong / moderate / weak
- Remaining gaps: list of concepts still not fully understood
- Recommended next step: one concrete suggestion

---

## Features

| Feature | Description |
|---|---|
| Adaptive diagnosis | 4-question diagnostic with ML shadow model for validation |
| Personalised lesson planning | Strategy chosen from 5 options based on diagnosis |
| Live whiteboard | Step-by-step rendering with KaTeX math notation |
| Voice narration | AWS Polly TTS per section (mock mode for local dev) |
| Mid-lesson interruptions | Student can ask questions; tutor answers in context |
| Resume from cursor | After interruption, lesson resumes at exact position |
| Understanding evaluation | 3 post-lesson questions, LLM-scored with gap analysis |
| Session persistence | Redis-backed live state, PostgreSQL audit trail |
| ML diagnosis layer | Parallel shadow ML model for diagnosis validation |
| Robust JSON parsing | `json-repair` library handles all LLM formatting errors |
| Connection retry | Redis operations retry 3× with exponential backoff |
| Toast notifications | User-friendly error messages (offline, server, session errors) |

---

## Technical Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vanilla JS)                 │
│  index.html · app.js · api.js · whiteboard.js · KaTeX  │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / REST
┌──────────────────────────▼──────────────────────────────┐
│                 Backend (FastAPI + Python)               │
│                                                         │
│  POST /api/session/create                               │
│  GET  /api/diagnosis/:id/questions                      │
│  POST /api/diagnosis/submit                             │
│  POST /api/session/:id/advance      ◄── main loop       │
│  POST /api/session/:id/interrupt                        │
│  POST /api/session/evaluate                             │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           LangGraph State Machine               │   │
│  │  plan_lesson → teach_section → evaluate → END   │   │
│  │                    ↕                            │   │
│  │            handle_interruption                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  Modules: input_understanding · diagnosis · lesson_     │
│  planner · tutoring_delivery · evaluation · interruption│
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
  ┌────────▼────────┐      ┌──────────▼──────────┐
  │  Redis (Upstash) │      │ PostgreSQL (Fly.io)  │
  │  Live session    │      │ Audit trail, ML data │
  │  state (4h TTL)  │      │ diagnosis records    │
  └─────────────────┘      └─────────────────────┘
```

### LangGraph Tutoring State Machine

The core orchestrator is a LangGraph `StateGraph` compiled with `interrupt_after` so the API drives it step-by-step:

```
plan_lesson → teach_section ──→ evaluate → END
                   ↕
           handle_interruption
```

Each `/advance` API call resumes the graph one step, returns a delivery package, and pauses again. This gives the frontend full control over pacing.

### LLM Stack

| Task | Model (Groq default) | Fallback |
|---|---|---|
| Input understanding | llama-3.1-8b-instant | claude-haiku / gpt-4o-mini |
| Diagnosis & lesson | llama-3.1-8b-instant | claude-haiku / gpt-4o-mini |
| Delivery content | llama-3.3-70b-versatile | claude-sonnet / gpt-4o |

Provider is configurable via `DEFAULT_LLM_PROVIDER` env var (`groq` / `anthropic` / `openai` / `cerebras`).

---

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL instance (local or cloud)
- Redis instance (local or cloud)
- API key for at least one LLM provider (Groq free tier works)

### Backend

```bash
git clone https://github.com/YOUR_USERNAME/AIMathTutor.git
cd AIMathTutor/backend

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env
# Edit .env — set DATABASE_URL, REDIS_URL, GROQ_API_KEY (minimum)

alembic upgrade head              # run database migrations
uvicorn app.main:app --reload --port 8003
```

### Frontend

Open `frontend/index.html` directly in a browser, or use any static file server:

```bash
cd frontend
npx serve .                       # or: python -m http.server 5500
```

The frontend auto-connects to `http://localhost:8003`. No build step required.

### Environment Variables (`.env.example`)

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
REDIS_URL=redis://localhost:6379

# LLM (set at least one)
GROQ_API_KEY=your_groq_key
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key

# LLM provider selection
DEFAULT_LLM_PROVIDER=groq          # groq | anthropic | openai | cerebras

# TTS (optional — defaults to mock)
TTS_PROVIDER=mock                  # mock | polly
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1

# CORS (production)
FRONTEND_ORIGINS=https://your-frontend.vercel.app
```

### Run Tests

```bash
cd backend
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_input_understanding.py -v
```

---

## Deployment

**Backend → Fly.io**
```bash
cd backend
fly launch
fly secrets set GROQ_API_KEY=... DATABASE_URL=... REDIS_URL=... FRONTEND_ORIGINS=...
fly deploy
```

**Frontend → Vercel**
```bash
cd frontend
vercel
```

---

## Project Structure

```
AIMathTutor/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app entry point
│   │   ├── core/
│   │   │   ├── config.py                    # Settings (reads .env)
│   │   │   ├── llm.py                       # LLM factory: get_llm("fast"|"rich")
│   │   │   └── structured_output.py         # RobustJsonOutputParser + helpers
│   │   ├── modules/
│   │   │   ├── input_understanding/         # Topic parsing from natural language
│   │   │   ├── diagnosis/                   # Adaptive diagnostic + ML shadow model
│   │   │   ├── lesson_planner/              # Personalised lesson plan generation
│   │   │   ├── tutoring_delivery/           # LangGraph orchestrator + delivery
│   │   │   ├── interruption/                # Mid-lesson question handling
│   │   │   └── evaluation/                  # Post-lesson scoring
│   │   ├── session/manager.py               # Redis session state
│   │   ├── models/schemas.py                # Pydantic models
│   │   └── api/routes/                      # REST endpoints
│   ├── data/
│   │   ├── question_banks/                  # Pre-written diagnostic questions
│   │   └── diagnosis_taxonomy/              # Topic metadata & misconception probes
│   ├── scripts/                             # ML training & data utilities
│   ├── tests/                               # pytest test suite
│   └── requirements.txt
├── frontend/
│   ├── index.html                           # Single-page app
│   └── src/
│       ├── css/main.css
│       └── js/
│           ├── api.js                       # Backend API client
│           ├── whiteboard.js                # KaTeX rendering + audio sync
│           ├── session.js                   # Client-side session state
│           └── app.js                       # Main UI controller
├── .env.example
├── PROJECT_BRIEF.md
└── README.md
```

---

## AI Usage Declaration

AI tools were used throughout the development of this project:

| Usage | Details |
|---|---|
| **Brainstorming & Design** | AI (Claude) used to explore architecture decisions, diagnose approach, LangGraph state machine design |
| **Code Development** | AI used as a coding copilot — suggesting implementations, refactoring, and writing boilerplate |
| **Testing** | AI assisted in writing unit tests (`tests/`) and reviewing test coverage |
| **Code Review** | AI reviewed code for correctness, security, and edge cases |
| **Runtime AI** | The product itself uses LLMs (Groq/Anthropic/OpenAI) to power diagnosis, lesson planning, delivery, and evaluation |

The core architecture decisions, system design, and product vision were made by the developer. AI was a development accelerator, not the decision-maker.

---

## Impact & Sustainability

**Impact**
- Removes the cost barrier to personalised university mathematics tutoring
- Available 24/7 — no scheduling, no waiting for office hours
- Adapts to each student's exact knowledge gaps and learning style
- Scales to any number of students simultaneously

**Sustainability**
- Hosted on Fly.io (backend) and Vercel (frontend) — minimal operational overhead
- LLM inference uses cost-efficient fast-tier models by default
- ML diagnosis layer improves automatically as more students use the system
- Designed for institutional licensing (universities, online learning platforms) and direct student subscription

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, LangChain, LangGraph |
| LLM | Groq (default), Anthropic Claude, OpenAI, Cerebras |
| Database | PostgreSQL — audit trail & ML training data |
| Session Cache | Redis — live session state |
| Frontend | Vanilla JS, HTML, CSS |
| Math Rendering | KaTeX (CDN) |
| TTS | AWS Polly (mock mode for local dev) |
| Backend Hosting | Fly.io |
| Frontend Hosting | Vercel |

---

## License

MIT
