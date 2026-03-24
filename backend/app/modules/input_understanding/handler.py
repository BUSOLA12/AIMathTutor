import uuid

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.structured_output import RobustJsonOutputParser, as_dict, get_float, get_string_list, get_text
from app.models.schemas import SessionResponse, TargetType

SUBJECT_AREAS = {
    "real_analysis",
    "calculus",
    "linear_algebra",
    "abstract_algebra",
    "topology",
    "other",
}
TARGET_TYPES = {target_type.value for target_type in TargetType}

INPUT_UNDERSTANDING_PROMPT = """You are a mathematical content analyzer.

Given the student's input, extract the following and respond ONLY with valid JSON:
{{
  "topic": "the exact mathematical concept, theorem, or proof (concise name)",
  "target_type": "concept" | "theorem_proof" | "definition" | "exercise",
  "subject_area": "real_analysis" | "calculus" | "linear_algebra" | "abstract_algebra" | "topology" | "other",
  "likely_prerequisites": ["list", "of", "prerequisite", "concepts"],
  "input_confidence": 0.0 to 1.0
}}

Student input: {input_text}"""


async def understand_input(input_text: str, session_id: str | None = None) -> SessionResponse:
    llm = get_llm("fast")
    prompt = ChatPromptTemplate.from_template(INPUT_UNDERSTANDING_PROMPT)
    chain = prompt | llm | RobustJsonOutputParser()

    result = as_dict(await chain.ainvoke({"input_text": input_text}))

    return SessionResponse(
        session_id=session_id or str(uuid.uuid4()),
        topic=get_text(result, "topic", input_text),
        target_type=get_text(result, "target_type", "concept", allowed=TARGET_TYPES),
        subject_area=get_text(result, "subject_area", "other", allowed=SUBJECT_AREAS),
        likely_prerequisites=get_string_list(result, "likely_prerequisites"),
        input_confidence=get_float(result, "input_confidence", 0.8, minimum=0.0, maximum=1.0),
    )
