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
| --- | --- |
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

## Machine Learning — The Diagnosis Engine

The heart of AI Math Tutor's intelligence is not just the LLM — it is a custom-trained supervised ML pipeline that learns *from every tutoring session* to diagnose students more accurately over time. This section explains the full ML system: what it learns, how it works, and how it is woven into the live tutoring flow.

---

### Why ML on top of an LLM?

An LLM alone can diagnose a student, but it is slow, expensive, and inconsistent across sessions. The ML layer adds:

- **Speed** — inference in <5 ms vs. ~2 s for an LLM call
- **Consistency** — same student profile → same diagnosis
- **Improvement** — gets better as more students use the system
- **Validation** — independently verifies the LLM's diagnosis to catch hallucinations

---

### Four Learning Tasks

The system trains one model per diagnosis output — four supervised learning problems in total:

| Task | Type | Output | Labels |
| --- | --- | --- | --- |
| **A — Learner level** | 4-class multiclass | `beginner` / `beginner_intermediate` / `intermediate` / `advanced` | Assigned by LLM on training data |
| **B — Missing prerequisites** | Hybrid rule + ML gate | List of gaps e.g. `["absolute_value", "quantifiers"]` | Topic-specific prerequisite vocabulary |
| **C — Misconception labels** | Multi-label classification | e.g. `["quantifier_confusion", "intuition_gap"]` | 7-class taxonomy |
| **D — Teaching strategy** | Single-label multiclass | `intuition_first` / `example_first` / `formal_definition_first` / `proof_first` / `prerequisite_micro_lesson_first` | Assigned by LLM on training data |

---

### Feature Engineering

Each student session is converted into a rich feature vector before being fed to the models. Two types of features are extracted:

#### 1. Text Features (TF-IDF)

The student's questions and answers are concatenated into a structured `combined_text` string:

```text
topic:epsilon_delta_definition
confidence:low
qid:real_analysis::q_limit_intuition time:slow question:what does it mean for a limit to exist answer:i think it means the function gets close to a value
qid:real_analysis::q_quantifier_meaning time:very_slow question:what does for all mean in math answer:i dont know
```

This is vectorised with **TF-IDF (1–2 ngrams, 5000 features)** — capturing vocabulary patterns like "i think", "don't know", topic key tokens, and canonical question IDs.

#### 2. Dense Behavioral Features

A fixed-length numerical vector is built alongside the text:

| Feature | What it captures |
| --- | --- |
| `probe_features` scores | Per-skill relevance weights from the topic taxonomy (e.g. how much this topic tests absolute value knowledge) |
| `reference_similarity` (mean, std, min, max) | How closely each answer matches the reference answers for that question |
| `response_times_sec` (mean, std, max — normalised ÷ 40) | Whether the student hesitated (slow → likely gap) |
| `confidence_self_report` | Student's self-declared confidence (0 = high, 0.5 = medium, 1.0 = low) |
| `answer_lengths` (word counts per question) | Verbosity signal — very short answers often indicate uncertainty |

Text and dense features are **horizontally concatenated** into one sparse matrix before training:

```python
X = hstack([TF-IDF(combined_text), StandardScaler(dense_features)])
```

---

### Model Architecture

#### Tasks A, C, D — Logistic Regression (bundled format)

Each model is saved as a `(tfidf, scaler, probe_keys, classifier)` tuple:

- Tasks A and D: standard `LogisticRegression(class_weight="balanced")` multiclass classifier
- Task C (misconceptions): `OneVsRestClassifier` wrapping Logistic Regression — one binary classifier per misconception label — with **per-label threshold tuning** using precision-recall curves to maximise F1 independently for each misconception type

```text
[Student answers] → combined_text → TF-IDF
                                              → hstack → LogReg → learner_level
[Student timings] → dense_features → Scaler
```

#### Task B — Hybrid Two-Stage (prerequisite gap detection)

Prerequisite labels are inherently topic-specific vocabulary — TF-IDF cannot generalise across topics. A different architecture is used:

```text
┌──────────────────────────────────────────────────────────┐
│ Stage 1 (Rule):  Taxonomy lookup                        │
│                                                          │
│  probe_features["absolute_value"] = 0.85 ≥ 0.70 ✓       │
│  probe_features["quantifiers"]    = 0.72 ≥ 0.70 ✓       │
│  probe_features["sequences"]      = 0.40 < 0.70 ✗       │
│                                                          │
│  → candidates = ["absolute_value", "quantifiers"]        │
└──────────────────────┬───────────────────────────────────┘
                       │ candidates found?
                       ▼
┌──────────────────────────────────────────────────────────┐
│ Stage 2 (ML Gate):  Behavior classifier                 │
│                                                          │
│  Features: response times, answer quality, confidence   │
│  (topic-agnostic → generalises to unseen topics)        │
│                                                          │
│  P(gap present) = 0.73 ≥ 0.45 threshold                 │
│  → missing_prerequisites = ["absolute_value",           │
│                              "quantifiers"]              │
└──────────────────────────────────────────────────────────┘
```

**Unknown topic fallback:** If the topic is not in the taxonomy, `probe_features` is empty → Stage 1 returns no candidates → output is `([], 0.0)` → the aggregate confidence stays low → the system silently uses the LLM's diagnosis instead.

---

### Training Pipeline

Training is driven by three scripts in `backend/scripts/`:

```text
generate_synthetic_diagnosis_dataset.py
        │
        │  Generates labelled sessions via LLM across 8+ topic scenarios
        │  (beginner/intermediate/advanced × different misconception profiles)
        ▼
data/training/synthetic_diagnosis.jsonl
        │
        ▼
train_diagnosis_baseline.py
        │
        │  Topic-aware train/validation split
        │  (holdout topics excluded from training to test generalisation)
        │
        │  Trains all 4 tasks → saves .pkl bundles + manifest.json
        ▼
data/models/diagnosis/
    learner_level.pkl
    recommended_teaching_strategy.pkl
    misconception_labels.pkl
    missing_prerequisites_behavior.pkl
    manifest.json                 ← version, thresholds, metrics, label sets
        │
        ▼
evaluate_diagnosis_models.py      ← prints full classification reports
```

Run the full pipeline:

```bash
cd backend
python scripts/generate_synthetic_diagnosis_dataset.py
python scripts/train_diagnosis_baseline.py
python scripts/evaluate_diagnosis_models.py
```

---

### How It Integrates Into the Live System

When a student submits their diagnostic answers, the system runs **LLM and ML in parallel**:

```python
live_result, shadow = await asyncio.gather(
    run_diagnosis(session_id, topic, ...),   # LLM path
    run_shadow_diagnosis(session_id, ...),   # ML path
)
```

Three operating modes (set via `DIAGNOSIS_MODE` env var):

| Mode | Behaviour |
| --- | --- |
| `llm` | LLM result always used. ML disabled. |
| `ml_shadow` | Both run in parallel. LLM result is used. ML result stored in DB for comparison and future training. *(default)* |
| `ml_primary` | ML result used when confidence ≥ `DIAGNOSIS_ML_PRIMARY_MIN_CONFIDENCE` (default 0.62). Falls back to LLM otherwise. |

The confidence score is the **mean of the four per-task probabilities**:

```python
confidence = mean([learner_conf, strategy_conf, missing_conf, misconception_conf])
```

---

### Self-Improving Feedback Loop

Every real student session generates new training data. A background worker processes each completed diagnosis:

```text
Student completes diagnosis
        │
        ▼
Diagnosis run saved to PostgreSQL (questions, answers, LLM labels)
        │
        ▼
Background worker (run_diagnosis_worker.py)
  · Canonicalises questions against taxonomy
  · Builds training record (combined_text + dense features)
  · Materialises record into diagnosis_materialized_records table
        │
        ▼
export_diagnosis_dataset.py → exports JSONL
        │
        ▼
Retrain → improved models → redeploy
```

Over time, as more students use the system, the ML models become more accurate — reducing LLM dependency, lowering cost, and improving diagnosis speed.

---

### Taxonomy — The Knowledge Map

The `data/diagnosis_taxonomy/real_analysis.json` file is the knowledge backbone. For each topic (e.g. `epsilon_delta_definition`), it defines:

- **Prerequisite skill probes** with relevance weights (e.g. `absolute_value: 0.9`, `quantifiers: 0.85`)
- **Misconception probes** (e.g. `quantifier_confusion: 0.8`)
- **Reference answers** per canonical question (used to compute `reference_similarity`)
- **Canonical question templates** matched across sessions for consistent feature extraction

This taxonomy is what makes the ML system *knowledgeable about mathematics* rather than a generic text classifier.

---

## Technical Architecture

```text
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

```text
plan_lesson → teach_section ──→ evaluate → END
                   ↕
           handle_interruption
```

Each `/advance` API call resumes the graph one step, returns a delivery package, and pauses again. This gives the frontend full control over pacing.

### LLM Stack

| Task | Model (Groq default) | Fallback |
| --- | --- | --- |
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
FRONTEND_ORIGINS=https://your-frontend.netlify.app
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

### Backend → Fly.io

```bash
cd backend
fly launch
fly secrets set GROQ_API_KEY=... DATABASE_URL=... REDIS_URL=... FRONTEND_ORIGINS=...
fly deploy
```

### Frontend → Netlify

```bash
cd frontend
npx netlify-cli deploy --dir .          # draft preview
npx netlify-cli deploy --dir . --prod   # production
```

---

## Project Structure

```text
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
| --- | --- |
| **Brainstorming & Design** | AI (Claude) used to explore architecture decisions, diagnosis approach, LangGraph state machine design |
| **Code Development** | AI used as a coding copilot — suggesting implementations, refactoring, and writing boilerplate |
| **Testing** | AI assisted in writing unit tests (`tests/`) and reviewing test coverage |
| **Code Review** | AI reviewed code for correctness, security, and edge cases |
| **Runtime AI** | The product itself uses LLMs (Groq/Anthropic/OpenAI) to power diagnosis, lesson planning, delivery, and evaluation |

The core architecture decisions, system design, and product vision were made by the developer. AI was a development accelerator, not the decision-maker.

---

## Impact & Sustainability

### Impact

- Removes the cost barrier to personalised university mathematics tutoring
- Available 24/7 — no scheduling, no waiting for office hours
- Adapts to each student's exact knowledge gaps and learning style
- Scales to any number of students simultaneously

### Sustainability

- Hosted on Fly.io (backend) and Netlify (frontend) — minimal operational overhead
- LLM inference uses cost-efficient fast-tier models by default
- ML diagnosis layer improves automatically as more students use the system
- Designed for institutional licensing (universities, online learning platforms) and direct student subscription

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, FastAPI, LangChain, LangGraph |
| LLM | Groq (default), Anthropic Claude, OpenAI, Cerebras |
| Database | PostgreSQL — audit trail & ML training data |
| Session Cache | Redis — live session state |
| Frontend | Vanilla JS, HTML, CSS |
| Math Rendering | KaTeX (CDN) |
| TTS | AWS Polly (mock mode for local dev) |
| Backend Hosting | Fly.io |
| Frontend Hosting | Netlify |

---

## License

MIT
