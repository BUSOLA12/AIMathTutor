from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.structured_output import RobustJsonOutputParser, as_dict, get_dict, get_string_list, get_text
from app.models.schemas import EvaluationResult

SCORE_PROMPT = """You are a math tutor evaluating a student's understanding after a lesson.

Topic: {topic}
Student's starting level: {learner_level}

Evaluation questions and student answers:
{qa_pairs}

Assess the student's understanding and respond ONLY with valid JSON:
{{
  "understanding_summary": {{
    "definition_understanding": "strong" | "moderate" | "weak",
    "intuition_understanding": "strong" | "moderate" | "weak",
    "proof_understanding": "strong" | "moderate" | "weak",
    "application_ability": "strong" | "moderate" | "weak"
  }},
  "remaining_gaps": ["list of concepts still not understood"],
  "recommended_next_step": "one concise sentence recommendation"
}}"""


async def score_evaluation(
    session_id: str,
    topic: str,
    learner_level: str,
    questions: list[str],
    answers: list[str],
) -> EvaluationResult:
    llm = get_llm("fast")
    prompt = ChatPromptTemplate.from_template(SCORE_PROMPT)
    chain = prompt | llm | RobustJsonOutputParser()

    qa_pairs = "\n".join(
        f"Q{i+1}: {q}\nA{i+1}: {a}" for i, (q, a) in enumerate(zip(questions, answers))
    )

    result = as_dict(await chain.ainvoke({
        "topic": topic,
        "learner_level": learner_level,
        "qa_pairs": qa_pairs,
    }))

    return EvaluationResult(
        session_id=session_id,
        understanding_summary=get_dict(result, "understanding_summary"),
        remaining_gaps=get_string_list(result, "remaining_gaps"),
        recommended_next_step=get_text(
            result,
            "recommended_next_step",
            "Review the topic once more.",
        ),
    )
