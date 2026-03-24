from typing import List, Literal, Optional
from enum import Enum

from pydantic import BaseModel, Field


class LearnerLevel(str, Enum):
    beginner = "beginner"
    beginner_intermediate = "beginner_intermediate"
    intermediate = "intermediate"
    advanced = "advanced"


class TeachingStrategy(str, Enum):
    intuition_first = "intuition_first"
    example_first = "example_first"
    formal_definition_first = "formal_definition_first"
    proof_first = "proof_first"
    prerequisite_micro_lesson_first = "prerequisite_micro_lesson_first"


class TargetType(str, Enum):
    concept = "concept"
    theorem_proof = "theorem_proof"
    definition = "definition"
    exercise = "exercise"


# --- Session ---

class SessionCreateRequest(BaseModel):
    input_text: str
    input_type: str = "concept_text"  # "concept_text" | "pasted_text" | "screenshot"


class SessionResponse(BaseModel):
    session_id: str
    topic: str
    target_type: str
    subject_area: str
    likely_prerequisites: List[str]
    input_confidence: float


class SessionState(BaseModel):
    session_id: str
    topic: str
    target_type: str
    subject_area: str = "real_analysis"
    learner_level: Optional[str] = None
    missing_prerequisites: List[str] = Field(default_factory=list)
    teaching_strategy: Optional[str] = None
    misconception_labels: List[str] = Field(default_factory=list)
    current_section: Optional[str] = None
    current_step: int = 0
    current_section_index: int = 0
    phase: str = "input"           # input | diagnosing | planning | teaching | interrupted | evaluating | done
    board_state_version: int = 0
    interruptions_count: int = 0
    interruption_text: str = ""
    current_package_id: Optional[str] = None
    current_step_id: Optional[str] = None
    resume_pending: bool = False
    resume_cursor: Optional["ResumeCursor"] = None


# --- Diagnosis ---

class DiagnosticQuestionResponse(BaseModel):
    session_id: str
    questions: List[str]


class DiagnosticAnswerRequest(BaseModel):
    session_id: str
    answers: List[str]
    response_times_sec: Optional[List[float]] = None
    confidence_self_report: Optional[str] = None


class DiagnosisResult(BaseModel):
    session_id: str
    learner_level: LearnerLevel
    missing_prerequisites: List[str]
    misconception_labels: List[str]
    recommended_teaching_strategy: TeachingStrategy
    diagnostic_confidence: float


# --- Lesson ---

class LessonPlan(BaseModel):
    session_id: str
    start_point: str
    sections: List[str]
    likely_confusion_points: List[str]


class AudioMarker(BaseModel):
    name: str
    time_ms: int


class DeliveryStep(BaseModel):
    step_id: str
    kind: Literal["heading", "text", "math", "highlight", "pause"]
    display_text: str = ""
    spoken_text: str = ""
    reveal_mode: Literal["instant", "token", "line"] = "instant"
    target: Optional[str] = None


class ResumeCursor(BaseModel):
    package_id: str
    section: str
    step_id: Optional[str] = None
    audio_offset_ms: int = 0


class DeliveryPackage(BaseModel):
    package_id: str
    section: str
    steps: List[DeliveryStep] = Field(default_factory=list)
    audio_url: Optional[str] = None
    audio_provider: Optional[str] = None
    audio_duration_ms: int = 0
    markers: List[AudioMarker] = Field(default_factory=list)
    transcript: str = ""
    resume_cursor: ResumeCursor


class TutorMessage(BaseModel):
    session_id: str
    section_type: str
    spoken_text: str
    board_events: List[dict] = Field(default_factory=list)


# --- Interruption ---

class InterruptionRequest(BaseModel):
    session_id: str
    question_text: str
    package_id: Optional[str] = None
    step_id: Optional[str] = None
    audio_offset_ms: int = 0


class InterruptionResponse(BaseModel):
    session_id: str
    response_text: str
    board_events: List[dict] = Field(default_factory=list)
    resume_from: str


# --- Evaluation ---

class EvaluationAnswerRequest(BaseModel):
    session_id: str
    questions: List[str]
    answers: List[str]


class EvaluationResult(BaseModel):
    session_id: str
    understanding_summary: dict
    remaining_gaps: List[str] = Field(default_factory=list)
    recommended_next_step: str


# --- Advance (step-by-step lesson delivery) ---

class AdvanceResponse(BaseModel):
    session_id: str
    phase: str                                    # "teaching" | "done"
    section: Optional[str] = None                # section name (while teaching)
    content: Optional[str] = None                # tutor's spoken text
    board_events: List[dict] = Field(default_factory=list)
    delivery_package: Optional[DeliveryPackage] = None
    evaluation_questions: Optional[List[str]] = None   # populated when phase == "done"
    lesson_sections: Optional[List[str]] = None        # populated on first advance (after plan)
    resume_pending: bool = False


SessionState.model_rebuild()
