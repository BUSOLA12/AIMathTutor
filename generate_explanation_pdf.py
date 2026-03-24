"""
Generates KS_MathTutor_Codebase_Explanation.pdf
Run with the project virtual environment:
  backend/.venv/Scripts/python generate_explanation_pdf.py
"""
from fpdf import FPDF


def _ascii(text: str) -> str:
    """Replace characters outside Latin-1 with safe ASCII equivalents."""
    return (
        text
        .replace("\u2014", "--")   # em dash
        .replace("\u2013", "-")    # en dash
        .replace("\u2018", "'")    # left single quote
        .replace("\u2019", "'")    # right single quote
        .replace("\u201c", '"')    # left double quote
        .replace("\u201d", '"')    # right double quote
        .replace("\u2026", "...")  # ellipsis
        .replace("\u03b5", "epsilon")  # epsilon
        .replace("\u03b4", "delta")    # delta
    )


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

SECTIONS = [
    {
        "heading": "KS Math Tutor — Complete Codebase Explanation",
        "level": 0,
        "body": (
            "This document is a complete, explicit walkthrough of the KS Math Tutor codebase. "
            "It explains every file, how each piece works, and how they are all connected — "
            "written so that someone seeing the project for the first time can understand it fully."
        ),
    },
    {
        "heading": "1. What This Application Does (The Big Picture)",
        "level": 1,
        "body": (
            "KS Math Tutor is an AI-powered, one-on-one math tutoring system. A student types "
            "something like 'Explain uniform continuity' and the system:\n\n"
            "  1. Figures out exactly what mathematical concept was requested.\n"
            "  2. Asks the student a few diagnostic questions to understand their knowledge level.\n"
            "  3. Builds a personalised lesson plan based on those answers.\n"
            "  4. Delivers the lesson one section at a time on a virtual whiteboard, with proper "
            "mathematical notation rendered on screen.\n"
            "  5. Allows the student to interrupt and ask questions at any time.\n"
            "  6. Finishes with an evaluation that checks whether the student understood.\n\n"
            "Every piece of code exists to serve one of those six steps."
        ),
    },
    {
        "heading": "2. The Tech Stack — What Each Tool Is and Why It Is Used",
        "level": 1,
        "body": (
            "FastAPI — A Python web framework. Its job is to listen for HTTP requests (the browser "
            "asking for questions, or submitting answers) and send back responses. Think of it as "
            "the post office: it receives letters (requests) and sends replies (responses).\n\n"
            "LangChain — A Python library that makes it easier to talk to AI language models (LLMs). "
            "Instead of writing raw API calls yourself, LangChain gives you building blocks — prompts, "
            "output parsers, chains — that you assemble together.\n\n"
            "LangGraph — Built on top of LangChain. It lets you define a stateful, multi-step "
            "workflow as a graph. A graph has nodes (functions that do work) and edges (paths "
            "between them). The tutoring session moves through: plan -> teach -> teach -> evaluate.\n\n"
            "Redis — An extremely fast in-memory key-value store. Think of it like a dictionary "
            "that lives on a server. It stores the live state of each tutoring session with a "
            "4-hour expiry. Used because it is very fast to read and write during an active session.\n\n"
            "PostgreSQL — A traditional relational database. It stores the permanent audit trail: "
            "every session ever created, every evaluation result. Unlike Redis, it never expires.\n\n"
            "SQLAlchemy — A Python library that lets you interact with PostgreSQL using Python "
            "objects instead of writing raw SQL queries.\n\n"
            "Pydantic — A Python library for defining data shapes. When a browser sends JSON data "
            "to the backend, Pydantic automatically validates it and converts it to a Python object. "
            "It catches errors before they reach your business logic.\n\n"
            "Anthropic Claude / OpenAI / Groq — The underlying AI language models. The system "
            "works with any of them — switch by changing one environment variable: DEFAULT_LLM_PROVIDER.\n\n"
            "KaTeX — A JavaScript library that renders mathematical notation in the browser. "
            "When the AI writes $\\epsilon > 0$, KaTeX turns that into a typeset epsilon symbol.\n\n"
            "Vanilla JS / HTML / CSS — The frontend uses plain browser technology with no framework "
            "like React. This keeps it simple and lightweight."
        ),
    },
    {
        "heading": "3. Project Structure — The Map",
        "level": 1,
        "body": (
            "KSProject/\n"
            "  backend/\n"
            "    app/\n"
            "      main.py              <- entry point: starts the server, configures CORS\n"
            "      core/\n"
            "        config.py          <- reads environment variables (.env file)\n"
            "        llm.py             <- factory: returns the right AI model based on config\n"
            "      db/\n"
            "        database.py        <- connects to PostgreSQL, provides DB sessions\n"
            "      models/\n"
            "        schemas.py         <- Pydantic data shapes (what JSON looks like)\n"
            "        tables.py          <- SQLAlchemy table definitions (what the DB looks like)\n"
            "      session/\n"
            "        manager.py         <- reads/writes Redis session state\n"
            "      modules/\n"
            "        input_understanding/handler.py  <- LLM extracts topic from student input\n"
            "        diagnosis/handler.py            <- LLM diagnoses student knowledge\n"
            "        lesson_planner/handler.py       <- LLM designs personalised lesson plan\n"
            "        tutoring_delivery/graph.py      <- LangGraph state machine (the heart)\n"
            "        interruption/handler.py         <- marks an interruption in session state\n"
            "        evaluation/handler.py           <- LLM scores student's final answers\n"
            "      api/routes/\n"
            "        session.py         <- HTTP endpoints for session management\n"
            "        diagnosis.py       <- HTTP endpoints for diagnostic questions/answers\n"
            "    data/question_banks/\n"
            "      real_analysis.json  <- pre-written diagnostic questions per topic\n"
            "  frontend/\n"
            "    index.html            <- the single HTML page the student sees\n"
            "    src/css/main.css      <- all the styling\n"
            "    src/js/\n"
            "      api.js              <- thin wrapper: calls the backend API\n"
            "      session.js          <- client-side memory of current state\n"
            "      whiteboard.js       <- renders lesson content on the whiteboard panel\n"
            "      app.js              <- main controller: wires together all user interactions"
        ),
    },
    {
        "heading": "4. Step 1 — The Student Types a Topic",
        "level": 1,
        "body": (
            "The student opens index.html, types 'Explain uniform continuity', and clicks "
            "'Start Session'.\n\n"
            "In app.js an event listener fires, collects the input text, and calls "
            "API.createSession(inputText). This function (defined in api.js) sends a POST "
            "request to http://localhost:8000/api/session/create with the text as a JSON body.\n\n"
            "FastAPI routes this to create_session() in api/routes/session.py. Pydantic "
            "automatically parses the JSON body into a SessionCreateRequest object — if any "
            "required field is missing, FastAPI returns a 422 error automatically, before your "
            "code even runs.\n\n"
            "Inside create_session():\n"
            "  - A unique session_id is generated (a UUID like '3f7e9b1a-...')\n"
            "  - understand_input(request.input_text, session_id) is called\n\n"
            "In modules/input_understanding/handler.py, the first LLM call happens:\n"
            "  llm = get_llm('fast')  <- returns the small/cheap AI model\n"
            "  chain = prompt | llm | JsonOutputParser()\n"
            "  result = await chain.ainvoke({'input_text': input_text})\n\n"
            "The | (pipe) syntax is LangChain: first build the prompt, send to the LLM, then "
            "parse the output as JSON. The LLM receives the student's text and extracts: topic, "
            "target_type (concept/theorem/definition), subject_area (real_analysis), likely "
            "prerequisites, and a confidence score.\n\n"
            "Back in create_session(), two things are saved:\n"
            "  1. A row is inserted into PostgreSQL's 'sessions' table (permanent record)\n"
            "  2. A SessionState object is serialised to JSON and stored in Redis under the "
            "key 'session:{session_id}' with a 4-hour TTL\n\n"
            "The SessionResponse (with session_id, topic, subject_area, etc.) is returned to "
            "the browser. app.js calls Session.init(session) to store this in client-side memory, "
            "then immediately fetches diagnostic questions."
        ),
    },
    {
        "heading": "5. Step 2 — Diagnostic Questions",
        "level": 1,
        "body": (
            "API.getDiagnosticQuestions(sessionId) calls GET /api/diagnosis/{session_id}/questions.\n\n"
            "In api/routes/diagnosis.py, get_questions() reads the session from Redis "
            "(get_session_state() does r.get('session:abc') and parses the JSON back into a "
            "SessionState object), then calls get_diagnostic_questions() in "
            "modules/diagnosis/handler.py.\n\n"
            "get_diagnostic_questions() is pure Python — no AI. It loads the JSON file at "
            "data/question_banks/real_analysis.json. That file is a dictionary of pre-written "
            "questions keyed by topic name. For 'uniform continuity', it converts to the key "
            "'uniform_continuity' and looks it up. If found, it returns up to 4 specific "
            "questions. If not found, it falls back to general math questions.\n\n"
            "Example entry in real_analysis.json:\n"
            "  'uniform_continuity': [\n"
            "    'What is the definition of continuity at a point?',\n"
            "    'What is the difference between pointwise and uniform continuity?',\n"
            "    'Can you give an example of a continuous function that is not uniformly "
            "continuous?',\n"
            "    'Would you like intuition first or the formal definition first?'\n"
            "  ]\n\n"
            "The questions come back to the frontend, app.js renders them as labelled text areas "
            "in the card-diagnosis panel, and shows that card while hiding card-topic."
        ),
    },
    {
        "heading": "6. Step 3 — Submitting Diagnostic Answers",
        "level": 1,
        "body": (
            "The student fills in their answers and clicks 'Submit Answers'. app.js collects the "
            "text from each textarea and calls API.submitDiagnosticAnswers(sessionId, answers) "
            "-> POST /api/diagnosis/submit.\n\n"
            "In api/routes/diagnosis.py, submit_answers() calls run_diagnosis() from "
            "modules/diagnosis/handler.py. This is the second LLM call:\n\n"
            "  chain = prompt | llm | JsonOutputParser()\n"
            "  result = await chain.ainvoke({'topic': topic, 'qa_pairs': qa_pairs, ...})\n\n"
            "The prompt tells the AI: 'Here are the diagnostic questions and the student's answers. "
            "Classify the student as beginner/intermediate/advanced, identify missing prerequisites, "
            "detect common misconceptions, and recommend a teaching strategy.'\n\n"
            "The DIAGNOSIS_PROMPT constrains the AI to choose misconception labels from a specific "
            "list: 'definition_confusion', 'quantifier_confusion', 'notation_confusion', etc. "
            "This forces structured, usable output.\n\n"
            "After diagnosis, these fields are saved back to Redis:\n"
            "  - state.learner_level = result.learner_level\n"
            "  - state.missing_prerequisites = result.missing_prerequisites\n"
            "  - state.teaching_strategy = result.recommended_teaching_strategy\n"
            "  - state.misconception_labels = result.misconception_labels\n"
            "  - state.phase = 'planning'\n\n"
            "The phase field changing to 'planning' is critical — the advance endpoint checks "
            "it to know whether this is the first lesson invocation.\n\n"
            "app.js shows a diagnosis summary on the whiteboard and displays a chat message: "
            "'I'll start with intuition_first. Press Continue to begin.' The lesson card is shown."
        ),
    },
    {
        "heading": "7. Step 4 — The Lesson: The LangGraph Engine",
        "level": 1,
        "body": (
            "When the student clicks 'Continue', app.js calls API.advanceSession(sessionId) "
            "-> POST /api/session/{session_id}/advance.\n\n"
            "advance_session() in api/routes/session.py checks the Redis phase:\n\n"
            "  if state.phase == 'planning':  <- FIRST click only\n"
            "      initial = { all state fields... }\n"
            "      result = await tutor_graph.ainvoke(initial, config=config)\n"
            "  else:  <- all subsequent clicks\n"
            "      result = await tutor_graph.ainvoke(None, config=config)\n\n"
            "Passing None means 'resume from where you paused last time'. The config dictionary "
            "contains thread_id = session_id so LangGraph knows which session to resume.\n\n"
            "--- THE LANGGRAPH STATE MACHINE ---\n\n"
            "Defined in modules/tutoring_delivery/graph.py. It has four nodes:\n\n"
            "  plan_lesson -> teach_section -> (loop or -> evaluate -> END)\n"
            "                      ^\n"
            "               handle_interruption\n\n"
            "TutoringState is a TypedDict: a Python dictionary with fixed, typed keys. Every "
            "node receives the full state and returns only the fields it changed. LangGraph "
            "merges those changes back into the state.\n\n"
            "Node 1: plan_lesson_node\n"
            "Runs once on the first Continue click. Calls plan_lesson() in "
            "lesson_planner/handler.py, which makes an LLM call (rich model): 'Design a lesson "
            "plan for {topic} at {learner_level} using {teaching_strategy} strategy.' Returns "
            "JSON like: {sections: ['motivation','intuition','formal_definition','example',"
            "'checkpoint','summary']}. The state's lesson_plan is populated.\n\n"
            "Node 2: teach_section_node\n"
            "Runs once per section. Reads current_section_index, gets sections[idx], calls the "
            "LLM (rich model): 'Teach this section conversationally. Use $...$ for math.' "
            "Appends the response to messages and board_events. Increments current_section_index.\n\n"
            "Node 3: handle_interruption_node\n"
            "Called when a student asks a question mid-lesson. Calls the LLM: 'The student asked "
            "{question}. Answer directly, then bridge back to the lesson.'\n\n"
            "Node 4: evaluate_node\n"
            "Runs after all sections. Calls the LLM (fast model) to generate 3 evaluation "
            "questions: one explain-back, one application, one misconception probe. Stores them "
            "in evaluation_questions. Sets phase = 'done'.\n\n"
            "--- WHY IT PAUSES ---\n\n"
            "The graph was compiled with:\n"
            "  interrupt_after=['teach_section', 'handle_interruption']\n\n"
            "This tells LangGraph: after teach_section_node finishes, save the state to the "
            "checkpointer (MemorySaver) and STOP. Return to the caller. Do not automatically "
            "run the next node. MemorySaver stores the full graph state in memory, indexed by "
            "thread_id. The next ainvoke(None, config) call resumes exactly where it left off.\n\n"
            "--- THE ROUTING FUNCTION ---\n\n"
            "After teach_section_node, route_after_teaching() decides the next node:\n"
            "  if interruption_pending -> handle_interruption\n"
            "  if current_section_index >= len(sections) -> evaluate\n"
            "  else -> teach_section (loop)\n\n"
            "advance_session() then reads the last message and board_event from the result, "
            "syncs the phase back to Redis, and returns an AdvanceResponse with the section "
            "name, content, and (on first advance) lesson_sections."
        ),
    },
    {
        "heading": "8. Frontend Rendering",
        "level": 1,
        "body": (
            "When app.js receives the AdvanceResponse:\n\n"
            "  // On first advance, store lesson plan sections in Session\n"
            "  if (response.lesson_sections && !Session.getLessonPlan()) {\n"
            "    Session.setLessonPlan({ sections: response.lesson_sections });\n"
            "  }\n\n"
            "  // If all sections done, switch to evaluation\n"
            "  if (response.phase === 'done') { ... show card-evaluation ... }\n\n"
            "  // Otherwise render the section content\n"
            "  addChatMessage('tutor', response.content);\n"
            "  Whiteboard.appendSection(response.section, response.content);\n"
            "  Whiteboard.highlightSection(response.section);\n\n"
            "whiteboard.js: appendSection() creates a styled <div> with a label and content. "
            "After inserting it into the DOM, it calls renderMathInElement() (KaTeX) on the new "
            "block. KaTeX scans for $...$ and $$...$$ and replaces them with rendered math symbols. "
            "highlightSection() draws a colored left border on the current section.\n\n"
            "addChatMessage() in app.js creates a chat bubble with the tutor's content in the "
            "right panel, also running KaTeX on it.\n\n"
            "session.js stores all client-side state: sessionId, topic, phase, diagnosisResult, "
            "lessonPlan, currentSectionIndex. It exposes only controlled getter/setter functions. "
            "Session.nextSection() increments currentSectionIndex. Session.isLessonComplete() "
            "returns true when currentSectionIndex >= sections.length (used to change the button "
            "label to 'Finish lesson')."
        ),
    },
    {
        "heading": "9. Step 5 — Interruption (Student Asks a Question)",
        "level": 1,
        "body": (
            "At any time during the lesson, the student can type in the input box and click 'Ask'. "
            "app.js adds the student's message to the chat and calls "
            "API.sendInterruption(sessionId, question) -> POST /api/session/{id}/interrupt.\n\n"
            "register_interruption() in modules/interruption/handler.py:\n"
            "  state.phase = 'interrupted'\n"
            "  state.interruption_text = question_text\n"
            "  state.interruptions_count += 1\n"
            "  await save_session_state(state)\n\n"
            "It just flags the session in Redis. The interruption is NOT handled immediately — "
            "it will be handled on the next 'Continue' click.\n\n"
            "When Continue is clicked, advance_session() reads phase='interrupted' from Redis:\n\n"
            "  tutor_graph.update_state(\n"
            "    config,\n"
            "    {'interruption_pending': True, 'interruption_text': state.interruption_text},\n"
            "  )\n"
            "  result = await tutor_graph.ainvoke(None, config=config)\n\n"
            "update_state() directly modifies the LangGraph's checkpointed state — it injects "
            "interruption_pending=True. Then ainvoke(None) resumes, route_after_teaching() "
            "sees interruption_pending=True, routes to handle_interruption_node, which answers "
            "the question and pauses (interrupt_after). The next Continue resumes the lesson "
            "from the next section."
        ),
    },
    {
        "heading": "10. Step 6 — Evaluation and Results",
        "level": 1,
        "body": (
            "When all lesson sections are complete, ainvoke() returns with phase='done' and "
            "evaluation_questions populated (3 questions generated by evaluate_node). app.js "
            "calls _buildEvaluationForm(evalQs) which renders labelled textareas for each "
            "question. card-lesson is hidden, card-evaluation is shown.\n\n"
            "The student fills in answers and clicks 'Submit'. app.js calls "
            "API.submitEvaluation(sessionId, questions, answers) -> POST /api/session/evaluate.\n\n"
            "In api/routes/session.py, submit_evaluation() calls score_evaluation() from "
            "modules/evaluation/handler.py. This is another LLM call (fast model):\n\n"
            "  'Here are the topic, student level, and their answers to 3 questions. Rate their "
            "understanding as strong/moderate/weak across these dimensions: "
            "definition_understanding, intuition_understanding, proof_understanding, "
            "application_ability.'\n\n"
            "The LLM returns a structured JSON with understanding_summary, remaining_gaps, "
            "and recommended_next_step. This is saved to Redis (phase='done') and returned "
            "to the browser.\n\n"
            "app.js renders the results in card-results: each understanding dimension with its "
            "strength level, remaining gaps, and the recommended next step. The student can "
            "then start a new topic (page reload)."
        ),
    },
    {
        "heading": "11. Redis vs PostgreSQL — Why Two Databases",
        "level": 1,
        "body": (
            "Junior engineers often ask: why use two databases?\n\n"
            "Redis (live state): During an active session, the backend reads and updates session "
            "state on every API call. Redis can do this in under 1 millisecond. It stores only "
            "what is needed RIGHT NOW: phase, learner_level, interruption_text, etc. It has a "
            "4-hour TTL because once a session is over, this data is no longer needed in fast "
            "memory.\n\n"
            "PostgreSQL (permanent record): This is the historical audit trail. The 'sessions' "
            "table stores every session ever created. The lesson_events, diagnostic_responses, "
            "and evaluation_results tables store what happened in each session. This data never "
            "expires. If the team wants analytics ('what topics are most requested?'), they "
            "query PostgreSQL.\n\n"
            "Note: In the current MVP, PostgreSQL tables are defined (in tables.py) but most "
            "events (lesson delivery, interruptions) are not yet being written to them — only "
            "session creation and evaluation results are. The table definitions are the blueprint "
            "for the full production data model."
        ),
    },
    {
        "heading": "12. The Schemas — schemas.py vs tables.py",
        "level": 1,
        "body": (
            "These two files define the same concepts in two different ways.\n\n"
            "schemas.py (Pydantic models) is used for:\n"
            "  - Validating and parsing incoming HTTP request bodies\n"
            "    (SessionCreateRequest, DiagnosticAnswerRequest, EvaluationAnswerRequest)\n"
            "  - Defining the shape of HTTP responses\n"
            "    (SessionResponse, AdvanceResponse, DiagnosisResult, EvaluationResult)\n"
            "  - Carrying data between Python functions\n"
            "    (SessionState, LessonPlan, DiagnosisResult)\n\n"
            "When a POST request arrives, FastAPI automatically parses the JSON body into the "
            "corresponding Pydantic model. Missing fields or wrong types cause a 422 error "
            "automatically — no explicit validation code needed.\n\n"
            "tables.py (SQLAlchemy ORM models) is used for:\n"
            "  - Defining the structure of PostgreSQL tables\n"
            "  - Performing database operations: db.add(SessionTable(...)) inserts a row\n\n"
            "These are kept separate because the HTTP API shape does not always match the "
            "database shape exactly.\n\n"
            "Key schema classes:\n"
            "  SessionState — the live Redis state (phase, topic, learner_level, etc.)\n"
            "  AdvanceResponse — what the /advance endpoint returns to the frontend\n"
            "  DiagnosisResult — the structured output of the diagnosis LLM call\n"
            "  LessonPlan — the structured output of the lesson planner LLM call\n"
            "  EvaluationResult — the structured output of the evaluation LLM call"
        ),
    },
    {
        "heading": "13. Configuration — core/config.py and .env",
        "level": 1,
        "body": (
            "config.py defines a Settings class using pydantic-settings:\n\n"
            "  class Settings(BaseSettings):\n"
            "      database_url: str = 'postgresql+asyncpg://...'\n"
            "      redis_url: str = 'redis://localhost:6379'\n"
            "      groq_api_key: str = ''\n"
            "      anthropic_api_key: str = ''\n"
            "      default_llm_provider: str = 'groq'\n"
            "      frontend_origins: str = ''\n\n"
            "BaseSettings automatically reads from environment variables AND from a .env file. "
            "So settings.anthropic_api_key returns whatever is in the ANTHROPIC_API_KEY "
            "environment variable. This is how secrets (API keys, database passwords) are "
            "kept out of the source code.\n\n"
            "The .env.example file in the project root is a template showing what variables "
            "need to be set before running the backend.\n\n"
            "allowed_frontend_origins is a computed property that reads FRONTEND_ORIGINS "
            "(comma-separated list) and returns it as a Python list. This is passed to the "
            "CORS middleware in main.py."
        ),
    },
    {
        "heading": "14. The LLM Factory — core/llm.py",
        "level": 1,
        "body": (
            "Every module that needs an AI model calls get_llm('fast') or get_llm('rich').\n\n"
            "  def get_llm(task: str = 'fast'):\n"
            "      provider = settings.default_llm_provider\n"
            "      if provider == 'groq':\n"
            "          model = 'llama-3.1-8b-instant' if task == 'fast'\n"
            "                  else 'llama-3.3-70b-versatile'\n"
            "          return ChatGroq(model=model, api_key=settings.groq_api_key)\n"
            "      if provider == 'anthropic':\n"
            "          model = 'claude-haiku-4-5-20251001' if task == 'fast'\n"
            "                  else 'claude-sonnet-4-6'\n"
            "          return ChatAnthropic(model=model, ...)\n\n"
            "'Fast' = small/cheap model for structured extraction tasks: diagnosis, evaluation "
            "scoring, input understanding, generating eval questions.\n\n"
            "'Rich' = large/capable model for long-form teaching content: lesson planning, "
            "section delivery, answering interruptions.\n\n"
            "By calling get_llm() everywhere instead of instantiating models directly, the "
            "entire codebase can switch AI providers by changing one environment variable. "
            "No other files need to change."
        ),
    },
    {
        "heading": "15. Async / Await — Why It Is Everywhere",
        "level": 1,
        "body": (
            "You will see 'async def' and 'await' throughout the Python backend. This is "
            "important to understand.\n\n"
            "When a normal Python function calls the database or an API, the entire program "
            "STOPS AND WAITS. If 100 students are using the tutor simultaneously, they all wait "
            "in a queue — one at a time.\n\n"
            "'async def' functions are coroutines — they can pause themselves while waiting for "
            "something slow (a database query, an LLM response taking 5 seconds) and let other "
            "work run in the meantime. 'await' is where the pause happens:\n\n"
            "  result = await tutor_graph.ainvoke(initial, config=config)\n"
            "  # Python pauses HERE (for ~5-10 seconds while the LLM generates)\n"
            "  # and handles other incoming requests during that wait\n"
            "  # then resumes here with the result\n\n"
            "This is why all Redis, database, and LLM calls use 'await'. FastAPI is built "
            "around this model — it can handle many concurrent students efficiently even though "
            "LLM calls are slow."
        ),
    },
    {
        "heading": "16. The Full Dependency Map",
        "level": 1,
        "body": (
            "Browser (index.html)\n"
            "  app.js            <- orchestrates all user interactions\n"
            "    api.js          <- HTTP calls to backend\n"
            "    session.js      <- client-side state (sessionId, phase, lessonPlan)\n"
            "    whiteboard.js   <- renders KaTeX math content\n\n"
            "Backend (FastAPI, port 8000)\n"
            "  main.py           <- CORS + router registration\n"
            "    /api/session/*  -> api/routes/session.py\n"
            "      /create       -> input_understanding/handler.py -> LLM (fast)\n"
            "      /advance      -> tutoring_delivery/graph.py\n"
            "                        plan_lesson_node   -> lesson_planner/handler.py -> LLM (rich)\n"
            "                        teach_section_node -> LLM (rich)\n"
            "                        handle_interruption -> LLM (rich)\n"
            "                        evaluate_node       -> LLM (fast)\n"
            "      /interrupt    -> interruption/handler.py -> Redis\n"
            "      /evaluate     -> evaluation/handler.py -> LLM (fast)\n"
            "    /api/diagnosis/*  -> api/routes/diagnosis.py\n"
            "      /questions    -> diagnosis/handler.py -> question_banks/*.json\n"
            "      /submit       -> diagnosis/handler.py -> LLM (fast)\n\n"
            "Data Stores\n"
            "  Redis             <- live session state (4-hour TTL)\n"
            "  PostgreSQL        <- permanent records (sessions, evaluations)\n\n"
            "LangGraph MemorySaver\n"
            "  In-memory graph checkpoints per session_id\n"
            "  (stores full TutoringState between 'Continue' clicks)"
        ),
    },
]


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

class TutorPDF(FPDF):
    ACCENT = (108, 127, 247)   # --accent: #6c7ff7
    DARK   = (26, 29, 39)      # --surface: #1a1d27
    LIGHT  = (232, 234, 246)   # --text: #e8eaf6

    def header(self):
        self.set_fill_color(*self.DARK)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.ACCENT)
        self.set_xy(0, 3)
        self.cell(0, 8, "KS Math Tutor -- Codebase Explanation", align="C")
        self.ln(8)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(140, 145, 180)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def title_page(self):
        self.add_page()

        self.set_font("Helvetica", "B", 28)
        self.set_text_color(*self.ACCENT)
        self.set_y(90)
        self.set_x(self.l_margin)
        self.cell(0, 14, "KS Math Tutor", align="C", new_x="LMARGIN", new_y="NEXT")

        self.set_font("Helvetica", "", 16)
        self.set_text_color(60, 60, 80)
        self.set_x(self.l_margin)
        self.cell(0, 10, "Complete Codebase Explanation", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(16)

        # Accent rule
        self.set_draw_color(*self.ACCENT)
        self.set_line_width(0.8)
        y_r = self.get_y()
        self.line(40, y_r, 170, y_r)
        self.set_xy(self.l_margin, y_r + 16)

        self.set_font("Helvetica", "", 11)
        self.set_text_color(80, 80, 100)
        self.set_x(self.l_margin)
        self.multi_cell(
            0, 7,
            "A deep, explicit walkthrough of every file and how\n"
            "they connect -- written for the junior engineer.",
            align="C",
        )

    def chapter(self, heading, level, body):
        self.add_page()
        heading = _ascii(heading)
        body = _ascii(body)

        # Heading
        if level == 0:
            self.set_font("Helvetica", "B", 18)
            self.set_text_color(*self.ACCENT)
        else:
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(*self.ACCENT)

        self.multi_cell(0, 8, heading)
        self.ln(3)

        # Horizontal rule
        self.set_draw_color(*self.ACCENT)
        self.set_line_width(0.4)
        y_rule = self.get_y()
        self.line(self.l_margin, y_rule, self.w - self.r_margin, y_rule)
        self.set_xy(self.l_margin, y_rule + 5)

        # Body
        for line in body.split("\n"):
            self.set_x(self.l_margin)
            if line.startswith("  ") or line.startswith("    "):
                # Indented code / diagram lines
                self.set_font("Courier", "", 8)
                self.set_text_color(100, 105, 140)
                self.multi_cell(0, 5, line)
            elif line.strip() == "":
                self.ln(3)
            else:
                self.set_font("Helvetica", "", 10)
                self.set_text_color(40, 40, 60)
                self.multi_cell(0, 6, line)


def build_pdf(output_path: str):
    pdf = TutorPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=15, top=16, right=15)

    pdf.title_page()

    for section in SECTIONS:
        pdf.chapter(section["heading"], section["level"], section["body"])

    pdf.output(output_path)
    print(f"PDF written to: {output_path}")


if __name__ == "__main__":
    build_pdf("KS_MathTutor_Codebase_Explanation.pdf")
