"""
LangGraph tutoring state machine.

Flow:
  plan_lesson → teach_section → (loop or → evaluate → END)
                     ↕
              handle_interruption

The graph is compiled with MemorySaver so each session's state is checkpointed
by session_id (passed as config["configurable"]["thread_id"]).
"""
from typing import List, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.core.structured_output import as_dict, get_string_list


class TutoringState(TypedDict):
    session_id: str
    topic: str
    subject_area: str
    target_type: str
    # Diagnosis outputs
    learner_level: str
    missing_prerequisites: List[str]
    misconceptions: List[str]
    teaching_strategy: str
    # Lesson
    lesson_plan: dict           # LessonPlan.model_dump()
    current_section_index: int
    # Delivery
    messages: List[dict]        # {"role": "tutor"|"student", "section": str, "content": str}
    board_events: List[dict]    # {"event_type": str, "section": str, "content": str}
    delivery_package: dict | None
    # Interruption
    interruption_pending: bool
    interruption_text: str
    # Evaluation
    evaluation_questions: List[str]
    # Phase
    phase: str  # planning | teaching | interrupted | evaluating | done


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def plan_lesson_node(state: TutoringState) -> dict:
    from app.models.schemas import DiagnosisResult, LearnerLevel, TeachingStrategy
    from app.modules.lesson_planner.handler import plan_lesson

    diagnosis = DiagnosisResult(
        session_id=state["session_id"],
        learner_level=state["learner_level"],
        missing_prerequisites=state["missing_prerequisites"],
        misconception_labels=state["misconceptions"],
        recommended_teaching_strategy=state["teaching_strategy"],
        diagnostic_confidence=0.8,
    )
    plan = await plan_lesson(state["topic"], diagnosis)
    return {
        "lesson_plan": plan.model_dump(),
        "current_section_index": 0,
        "phase": "teaching",
    }


async def teach_section_node(state: TutoringState) -> dict:
    from app.modules.tutoring_delivery.delivery import get_or_build_section_package

    sections = state["lesson_plan"].get("sections", [])
    idx = state["current_section_index"]

    if idx >= len(sections):
        return {"phase": "evaluating", "delivery_package": None}

    section = sections[idx]
    package = await get_or_build_section_package(
        session_id=state["session_id"],
        topic=state["topic"],
        learner_level=state["learner_level"],
        teaching_strategy=state["teaching_strategy"],
        section=section,
        messages=state.get("messages", []),
        section_index=idx,
    )

    message = {"role": "tutor", "section": section, "content": package.transcript}
    board_event = {
        "event_type": "delivery_package",
        "section": section,
        "package_id": package.package_id,
    }

    return {
        "messages": state["messages"] + [message],
        "board_events": state["board_events"] + [board_event],
        "delivery_package": package.model_dump(mode="json"),
        "current_section_index": idx + 1,
        "phase": "teaching",
    }


async def handle_interruption_node(state: TutoringState) -> dict:
    from app.modules.tutoring_delivery.delivery import build_interruption_package

    sections = state["lesson_plan"].get("sections", [])
    idx = max(0, state["current_section_index"] - 1)
    current_section = sections[idx] if idx < len(sections) else "lesson"
    package = await build_interruption_package(
        session_id=state["session_id"],
        topic=state["topic"],
        section=current_section,
        question=state["interruption_text"],
    )

    message = {"role": "tutor", "section": "interruption", "content": package.transcript}
    return {
        "messages": state["messages"] + [message],
        "delivery_package": package.model_dump(mode="json"),
        "interruption_pending": False,
        "interruption_text": "",
        "phase": "teaching",
    }


async def evaluate_node(state: TutoringState) -> dict:
    from langchain_core.prompts import ChatPromptTemplate
    from app.core.llm import get_llm
    from app.core.structured_output import RobustJsonOutputParser

    EVAL_PROMPT = (
        "You are a math tutor generating final understanding check questions.\n\n"
        "Topic taught: {topic}\n"
        "Student level at start: {learner_level}\n"
        "Sections covered: {sections}\n\n"
        "Generate exactly 3 questions covering:\n"
        "1. Explain-back (can the student restate the key idea?)\n"
        "2. Application (can the student apply it to a specific case?)\n"
        "3. Misconception check (probe a known misconception for this topic)\n\n"
        "Respond ONLY with JSON: {{\"questions\": [\"q1\", \"q2\", \"q3\"]}}"
    )

    llm = get_llm("fast")
    prompt = ChatPromptTemplate.from_template(EVAL_PROMPT)
    chain = prompt | llm | RobustJsonOutputParser()

    result = as_dict(await chain.ainvoke({
        "topic": state["topic"],
        "learner_level": state["learner_level"],
        "sections": ", ".join(state["lesson_plan"].get("sections", [])),
    }))

    questions = get_string_list(
        result,
        "questions",
        default=[
            f"What is the main idea behind {state['topic']}?",
            f"How would you apply {state['topic']} in a concrete example?",
            f"What is a common mistake someone might make with {state['topic']}?",
        ],
    )
    intro = "Great — let's check your understanding with three questions:\n\n"
    body = "\n\n".join(f"**{i+1}.** {q}" for i, q in enumerate(questions))
    message = {"role": "tutor", "section": "evaluation", "content": intro + body}

    return {
        "messages": state["messages"] + [message],
        "evaluation_questions": questions,
        "delivery_package": None,
        "phase": "done",
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_teaching(state: TutoringState) -> str:
    if state.get("interruption_pending"):
        return "handle_interruption"
    sections = state["lesson_plan"].get("sections", [])
    if state["current_section_index"] >= len(sections):
        return "evaluate"
    return "teach_section"


# ---------------------------------------------------------------------------
# Build & compile
# ---------------------------------------------------------------------------

workflow = StateGraph(TutoringState)
workflow.add_node("plan_lesson", plan_lesson_node)
workflow.add_node("teach_section", teach_section_node)
workflow.add_node("handle_interruption", handle_interruption_node)
workflow.add_node("evaluate", evaluate_node)

workflow.set_entry_point("plan_lesson")
workflow.add_edge("plan_lesson", "teach_section")
workflow.add_conditional_edges(
    "teach_section",
    route_after_teaching,
    {
        "handle_interruption": "handle_interruption",
        "evaluate": "evaluate",
        "teach_section": "teach_section",
    },
)
workflow.add_edge("handle_interruption", "teach_section")
workflow.add_edge("evaluate", END)

memory = MemorySaver()
tutor_graph = workflow.compile(
    checkpointer=memory,
    interrupt_after=["teach_section", "handle_interruption"],
)
