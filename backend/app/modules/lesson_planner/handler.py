from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.structured_output import RobustJsonOutputParser, as_dict, get_string_list, get_text
from app.models.schemas import DiagnosisResult, LessonPlan

DEFAULT_SECTIONS = [
    "motivation",
    "intuition",
    "formal_definition",
    "example",
    "checkpoint",
    "summary",
]

LESSON_PLAN_PROMPT = """You are an expert math tutor designing a personalized lesson plan.

Topic: {topic}
Student level: {learner_level}
Missing prerequisites: {missing_prerequisites}
Recommended teaching strategy: {teaching_strategy}
Misconceptions detected: {misconceptions}

Design a structured lesson plan. If missing_prerequisites is non-empty, start with a short
prerequisite recap before the main lesson.

Match the section order to the recommended teaching strategy:
- intuition_first: motivation → intuition → example → formal_definition → proof → checkpoint → summary
- example_first: motivation → example → intuition → formal_definition → proof → checkpoint → summary
- formal_definition_first: motivation → formal_definition → example → proof → checkpoint → summary
- proof_first: motivation → formal_definition → proof → example → checkpoint → summary
- prerequisite_micro_lesson_first: prerequisite_recap → motivation → intuition → formal_definition → proof → checkpoint → summary

Respond ONLY with valid JSON:
{{
  "start_point": "one-sentence description of where the lesson begins",
  "sections": ["section_name_1", "section_name_2", ...],
  "likely_confusion_points": ["anticipated confusion 1", "anticipated confusion 2"]
}}"""


async def plan_lesson(topic: str, diagnosis: DiagnosisResult) -> LessonPlan:
    llm = get_llm("rich")
    prompt = ChatPromptTemplate.from_template(LESSON_PLAN_PROMPT)
    chain = prompt | llm | RobustJsonOutputParser()

    result = as_dict(await chain.ainvoke({
        "topic": topic,
        "learner_level": diagnosis.learner_level,
        "missing_prerequisites": ", ".join(diagnosis.missing_prerequisites) or "none",
        "teaching_strategy": diagnosis.recommended_teaching_strategy,
        "misconceptions": ", ".join(diagnosis.misconception_labels) or "none",
    }))

    sections = get_string_list(result, "sections")
    if not sections:
        sections = DEFAULT_SECTIONS.copy()

    return LessonPlan(
        session_id=diagnosis.session_id,
        start_point=get_text(result, "start_point", "intuition"),
        sections=sections,
        likely_confusion_points=get_string_list(result, "likely_confusion_points"),
    )
