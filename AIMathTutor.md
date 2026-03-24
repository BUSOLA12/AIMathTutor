# AI Math Tutor System Documentation

## 1. Document Overview

This document defines the architecture, modules, responsibilities, data flow, interfaces, implementation scope, and development guidance for the **AI Math Tutor System**.

The system is designed to help students understand a **single mathematical concept, proof, definition, theorem, or exercise** through an interactive tutoring experience. The tutor accepts a concept request or uploaded material, diagnoses the learner’s level, plans a lesson, teaches through a live whiteboard-style explanation, answers interruptions, and evaluates understanding.

This documentation is intended to serve as a **technical implementation blueprint**.

---

## 2. Product Vision

### 2.1 Problem Statement

Students often struggle with university-level mathematics because existing materials are:

* too static
* too compressed
* not adaptive to their current level
* weak at revealing hidden intermediate steps
* unable to respond at the exact moment of confusion

The AI Math Tutor System addresses this by providing a **live, adaptive, concept-focused tutoring workflow**.

### 2.2 Core Goal

Help a student understand **one mathematical idea at a time** through:

* personalized diagnosis
* structured explanation
* step-by-step proof walkthroughs
* active questioning
* interruption-aware tutoring
* understanding checks

### 2.3 Initial MVP Focus

The initial MVP should focus on:

* one concept at a time
* university mathematics
* real analysis or closely related topics
* live whiteboard-style explanation with voice
* student diagnosis before teaching begins

---

## 3. High-Level System Summary

### 3.1 Main User Flow

1. Student submits input
2. System interprets the input
3. System identifies the target concept or proof
4. System diagnoses the student’s current understanding
5. System creates a lesson plan
6. System starts a live tutoring session
7. Student can interrupt at any time
8. System resumes the lesson after answering
9. System evaluates understanding
10. System stores session data for improvement and analytics

### 3.2 Major Modules

The system consists of the following core modules:

1. **Input Acquisition Module**
2. **Input Understanding Module**
3. **Student Diagnosis Module**
4. **Lesson Planning Module**
5. **Tutoring Delivery Module**
6. **Whiteboard Rendering Module**
7. **Interruption and Resume Module**
8. **Understanding Evaluation Module**
9. **Session State Manager**
10. **Data Storage and Analytics Module**

---

## 4. Functional Requirements

### 4.1 Student Capabilities

The student should be able to:

* enter a concept in text form
* paste a theorem, proof, or note excerpt
* upload a screenshot containing mathematical content
* answer diagnostic questions
* receive a live lesson
* interrupt the lesson with questions
* ask for slower explanation or additional examples
* receive final understanding checks

### 4.2 System Capabilities

The system should be able to:

* parse student inputs
* extract mathematical targets from raw input
* infer likely prerequisite concepts
* diagnose learner level
* recommend the best teaching entry point
* generate a lesson plan
* speak and write simultaneously
* pause and resume lessons cleanly
* track student confusion points
* evaluate understanding at the end of the session

---

## 5. Non-Functional Requirements

### 5.1 Accuracy

* Mathematical explanations should be as correct as possible.
* The system should reduce hallucinations through structure and grounding.

### 5.2 Responsiveness

* Diagnostic questioning should start quickly.
* Interruption handling should feel immediate.
* Whiteboard updates should appear in near real time.

### 5.3 Explainability

* The system should be able to justify why it started from a specific prerequisite.
* Internal diagnosis outputs should be interpretable for debugging.

### 5.4 Modularity

Each module should be independently testable and replaceable.

### 5.5 Extensibility

The architecture should support later additions such as:

* more subjects
* multi-concept lessons
* richer visual whiteboards
* persistent learner profiles
* spaced repetition

---

## 6. Module-by-Module Documentation

# 6.1 Input Acquisition Module

## Purpose

Collect raw student input from the interface.

## Supported Input Types

1. **Concept text**

   * Example: “Explain uniform continuity”
2. **Pasted text excerpt**

   * Example: theorem statement or proof paragraph
3. **Screenshot image**

   * Example: textbook snippet, lecture slide, handwritten note

## Responsibilities

* accept user input from frontend
* validate file type and size
* normalize text input
* forward raw content to the Input Understanding Module

## Inputs

* raw text
* image file
* metadata such as timestamp and session ID

## Outputs

* normalized input package

## Data Structure Example

```json
{
  "session_id": "sess_001",
  "input_type": "concept_text",
  "content": "Explain Cauchy sequences",
  "timestamp": "2026-03-10T10:00:00Z"
}
```

## MVP Notes

* Start with text and screenshot only.
* PDF and full document uploads can come later.

---

# 6.2 Input Understanding Module

## Purpose

Transform the raw student input into a structured mathematical target.

## Main Objective

Answer these questions:

* What exactly does the student want to understand?
* Is the target a concept, theorem, proof, definition, or exercise?
* Which mathematical terms and symbols are involved?
* What prerequisites are likely needed?

## Responsibilities

* parse text input
* perform OCR or vision-based extraction for screenshots
* identify mathematical topic
* identify target type
* detect likely course area
* infer likely prerequisite concepts

## Inputs

* normalized input package from the Input Acquisition Module

## Outputs

A structured target representation.

## Output Example

```json
{
  "session_id": "sess_001",
  "target_type": "theorem_proof",
  "topic": "convergent sequence implies bounded",
  "subject_area": "real_analysis",
  "symbols_detected": ["x_n", "L", "epsilon"],
  "likely_prerequisites": [
    "sequence",
    "convergence",
    "boundedness",
    "epsilon definition"
  ],
  "input_confidence": 0.88
}
```

## Possible Implementation Approaches

### Text inputs

* rule-based keyword detection
* LLM-based semantic parsing
* embeddings-based classification

### Image inputs

* OCR for plain text extraction
* vision-language model for math-aware extraction
* optional formula parsing pipeline

## MVP Implementation Recommendation

Use a combination of:

* OCR or vision model for screenshots
* LLM prompt for extracting structured target fields

## Risks

* OCR errors on math notation
* ambiguous student requests
* incorrect prerequisite inference

---

# 6.3 Student Diagnosis Module

## Purpose

Estimate the learner’s current understanding and determine where the tutoring session should begin.

## Importance

This is the most important custom intelligence module and the best candidate for your trained ML component.

## Main Questions This Module Must Answer

* What is the student’s current level?
* What prerequisite knowledge is missing?
* What kind of misunderstanding is present?
* What teaching style should be used first?
* How deep should the lesson start?

## Responsibilities

* generate diagnostic questions
* collect student answers
* analyze answer quality
* classify learner level
* identify missing prerequisites
* detect misconception categories
* output recommended teaching strategy

## Inputs

* structured target representation
* student responses to diagnostic questions
* optional metadata such as response time and confidence

## Outputs

```json
{
  "session_id": "sess_001",
  "learner_level": "beginner_intermediate",
  "missing_prerequisites": [
    "formal convergence definition",
    "difference between boundedness and convergence"
  ],
  "misconception_labels": [
    "incorrect implication"
  ],
  "recommended_teaching_strategy": "intuition_then_example_then_formal_proof",
  "diagnostic_confidence": 0.81
}
```

## Diagnosis Workflow

### Step 1: Question Generation

The module prepares 2 to 5 short diagnostic questions based on the target topic.

Example for convergent sequence implies bounded:

* What does it mean for a sequence to converge?
* Is every bounded sequence convergent?
* Would you like intuition first or proof first?

### Step 2: Response Collection

The student answers by text or voice.

### Step 3: Feature Extraction

Possible features:

* correctness score
* answer completeness
* terminology usage
* response confidence
* response length
* number of hints required
* misconception pattern

### Step 4: Prediction

A trained ML model predicts:

* learner level
* missing prerequisites
* misconception type
* preferred starting mode

### Step 5: Diagnostic Summary Generation

The module packages the result and sends it to the Lesson Planning Module.

## Training Opportunities

This is where you can apply ML and AI concepts.

### Candidate Prediction Tasks

1. learner level classification
2. prerequisite gap detection
3. misconception classification
4. teaching strategy recommendation

### Possible Models

* Logistic Regression
* Random Forest
* XGBoost
* simple neural network
* transformer-based classifier for student answers

### Recommended MVP Model

A simple multi-stage pipeline:

1. LLM or rules extract answer features
2. tabular ML model predicts labels

## Suggested Labels

### Learner level

* beginner
* beginner_intermediate
* intermediate
* advanced

### Missing prerequisite labels

* notation
* definition understanding
* convergence
* boundedness
* continuity
* proof logic
* quantifier reasoning

### Misconception labels

* wrong implication
* notation confusion
* theorem-definition confusion
* intuition gap
* proof-step gap

### Teaching strategy labels

* intuition_first
* example_first
* formal_definition_first
* proof_first
* prerequisite_micro_lesson_first

## Evaluation Metrics

* accuracy
* F1 score
* confusion matrix
* per-label precision and recall

## Risks

* small training data
* noisy labels
* student self-report may be unreliable
* response language may be vague

---

# 6.4 Lesson Planning Module

## Purpose

Build a structured teaching plan tailored to the diagnosed learner.

## Responsibilities

* choose the lesson start point
* order the explanation flow
* include prerequisite micro-lessons if needed
* choose examples and counterexamples
* insert checkpoint questions
* mark likely confusion points

## Inputs

* structured target representation
* diagnosis output

## Outputs

A lesson plan object.

## Output Example

```json
{
  "session_id": "sess_001",
  "lesson_plan": {
    "start_point": "convergence intuition",
    "sections": [
      "why_this_matters",
      "intuition",
      "formal_definition",
      "example",
      "theorem_statement",
      "proof_walkthrough",
      "checkpoint_question",
      "summary",
      "final_check"
    ],
    "likely_confusion_points": [
      "epsilon choice",
      "tail boundedness",
      "finite prefix argument"
    ],
    "question_schedule": [
      "after_definition",
      "after_proof_step_2",
      "before_summary"
    ]
  }
}
```

## Lesson Design Principles

For mathematics, the typical order should be:

1. motivation
2. intuition
3. formal definition
4. example
5. non-example
6. theorem or proof
7. checkpoint
8. summary
9. application check

## MVP Recommendation

Use prompt-driven lesson planning with strong structure constraints.

---

# 6.5 Tutoring Delivery Module

## Purpose

Execute the lesson plan as a live tutoring session.

## Responsibilities

* narrate the lesson
* coordinate with the whiteboard renderer
* explain step by step
* ask scheduled questions
* adapt based on student responses

## Inputs

* lesson plan
* current session state
* student responses during lesson

## Outputs

* spoken explanation stream
* teaching events for whiteboard updates
* checkpoint questions

## Delivery Style Requirements

The tutoring style should:

* sound like a private tutor
* explain symbols explicitly
* reveal hidden reasoning steps
* avoid jumping too quickly
* adapt pacing to student responses

## Example Tutor Actions

* explain definition
* introduce example
* write proof step
* ask reasoning question
* repeat in simpler language
* slow down after confusion

---

# 6.6 Whiteboard Rendering Module

## Purpose

Present mathematical content visually in a live whiteboard style.

## Responsibilities

* render math expressions clearly
* render step-by-step writing events
* synchronize writing with narration
* highlight important symbols or proof steps
* support pause and resume

## Inputs

* whiteboard events from Tutoring Delivery Module

## Outputs

* rendered math board state
* visual progression of explanation

## Whiteboard Event Example

```json
{
  "event_type": "write_math",
  "content": "|x_n - L| < 1",
  "position": "board_main",
  "timing_ms": 5200
}
```

## MVP Recommendation

Start with typed mathematical rendering rather than full handwriting generation.

### MVP Visual Features

* LaTeX rendering
* line-by-line board updates
* simple highlights
* section headers

## Future Enhancements

* animated handwriting
* diagram support
* multiple board panes

---

# 6.7 Interruption and Resume Module

## Purpose

Handle student interruptions without breaking lesson coherence.

## Responsibilities

* detect interruption intent
* pause lesson flow
* classify interruption type
* route to appropriate explanation behavior
* maintain lesson state
* resume from the exact prior point

## Interruption Types

* clarification request
* request for example
* slow-down request
* notation explanation request
* prerequisite gap request
* proof-step question

## Inputs

* live student question during lesson
* current session state

## Outputs

* interruption response
* updated lesson state
* resume event

## Core State Requirements

The module must know:

* current lesson section
* current proof step
* unresolved student confusion points
* whether the system is in the main lesson or side explanation
* resume pointer

## Example Resume State

```json
{
  "current_section": "proof_walkthrough",
  "current_step": 3,
  "side_explanation_active": true,
  "resume_target": {
    "section": "proof_walkthrough",
    "step": 3
  }
}
```

## Resume Rules

After interruption handling, the system should:

1. restate where it paused
2. connect the side explanation to the main lesson
3. continue from the exact step

## MVP Recommendation

Use explicit session state objects rather than trying to infer context from raw conversation only.

---

# 6.8 Understanding Evaluation Module

## Purpose

Estimate whether the student has understood the concept after the lesson.

## Responsibilities

* ask final understanding questions
* assess answer quality
* identify remaining weak points
* produce an understanding summary

## Inputs

* target concept
* completed lesson state
* student final answers

## Outputs

```json
{
  "session_id": "sess_001",
  "understanding_summary": {
    "definition_understanding": "strong",
    "intuition_understanding": "moderate",
    "proof_understanding": "partial",
    "application_ability": "partial"
  },
  "remaining_gaps": [
    "finite-prefix argument"
  ],
  "recommended_next_step": "review proof with one more example"
}
```

## Recommended Evaluation Pattern

Ask 3 types of questions:

1. **Explain-back question**
2. **Application question**
3. **Misconception check**

## Example

For convergent sequence implies bounded:

* Explain-back: Why does convergence imply boundedness?
* Application: If a sequence converges to 5, why must it be bounded?
* Misconception check: Is every bounded sequence convergent?

## MVP Recommendation

Keep evaluation short and concept-specific.

---

# 6.9 Session State Manager

## Purpose

Maintain the live internal state of the tutoring session.

## Responsibilities

* store current topic
* track lesson position
* track diagnosis output
* track interruptions
* maintain resume pointers
* store student progress indicators

## Why This Matters

Without a session state manager, the system will lose coherence during interruptions and adaptive teaching.

## Suggested State Fields

```json
{
  "session_id": "sess_001",
  "topic": "convergent sequence implies bounded",
  "target_type": "theorem_proof",
  "learner_level": "beginner_intermediate",
  "missing_prerequisites": ["formal convergence definition"],
  "current_section": "proof_walkthrough",
  "current_step": 3,
  "interruptions": [],
  "board_state_version": 12,
  "understanding_estimates": {
    "definition": "moderate",
    "proof_logic": "weak"
  }
}
```

---

# 6.10 Data Storage and Analytics Module

## Purpose

Store session data for system improvement, debugging, model training, and progress analytics.

## Responsibilities

* save raw inputs
* save diagnosis responses
* save model outputs
* save lesson plans
* save interruptions and checkpoints
* save evaluation results

## Stored Data Categories

* student session metadata
* input type and content
* diagnosis questions and answers
* predicted learner profile
* tutoring events
* interruption logs
* evaluation outcomes

## Important Note

If working with real users, privacy and consent need to be considered.

---

## 7. End-to-End Data Flow

### Step 1

Input Acquisition Module receives a concept, text, or screenshot.

### Step 2

Input Understanding Module extracts the target concept, target type, symbols, and prerequisites.

### Step 3

Student Diagnosis Module asks diagnostic questions and predicts student state.

### Step 4

Lesson Planning Module generates a personalized lesson sequence.

### Step 5

Tutoring Delivery Module executes the lesson.

### Step 6

Whiteboard Rendering Module displays the explanation visually.

### Step 7

Interruption and Resume Module handles student questions during teaching.

### Step 8

Understanding Evaluation Module measures what the student understood.

### Step 9

Data Storage Module saves the session for analytics and model iteration.

---

## 8. Diagnosis Module Technical Design

This section is provided because the diagnosis module is the best place for your trained model.

### 8.1 Problem Formulation

The diagnosis module can be modeled as one or more supervised learning tasks.

#### Task A: Learner Level Classification

Input: diagnostic answers and features
Output: beginner / intermediate / advanced

#### Task B: Prerequisite Gap Detection

Input: target concept + student answers
Output: missing prerequisite labels

#### Task C: Misconception Classification

Input: student answers
Output: misconception category

#### Task D: Teaching Strategy Recommendation

Input: learner features + target concept
Output: best initial teaching mode

### 8.2 Possible Input Features

#### Structured Features

* concept category
* number of correct answers
* response length
* answer confidence
* number of clarifications needed
* response latency

#### Semantic Features

* embedding of student answer
* similarity to ideal answer
* presence of key mathematical terms
* evidence of misconception phrases

### 8.3 Training Data Format Example

```json
{
  "topic": "convergent sequence implies bounded",
  "question_1": "What does it mean for a sequence to converge?",
  "answer_1": "It approaches a number.",
  "question_2": "Is every bounded sequence convergent?",
  "answer_2": "Yes.",
  "features": {
    "correct_count": 1,
    "misconception_signal": "wrong_implication",
    "answer_style": "informal",
    "confidence_level": "medium"
  },
  "labels": {
    "learner_level": "beginner_intermediate",
    "missing_prerequisite": [
      "difference between boundedness and convergence"
    ],
    "misconception": "wrong_implication",
    "teaching_strategy": "intuition_first"
  }
}
```

### 8.4 Recommended Initial Training Strategy

* build a small labeled dataset
* start with synthetic data if necessary
* use a simple classifier first
* evaluate by label quality and usefulness in tutoring

### 8.5 Synthetic Data Strategy

You can manually create diagnosis examples for topics such as:

* convergence
* boundedness
* Cauchy sequence
* continuity
* uniform continuity
* compactness

For each topic, create examples of:

* strong answer
* partial answer
* wrong implication
* notation confusion
* intuition-only answer
* formal but incomplete answer

---

## 9. API and Interface Contracts

This section defines how modules can communicate.

### 9.1 Input Understanding API Output

```json
{
  "target_type": "concept",
  "topic": "uniform continuity",
  "subject_area": "real_analysis",
  "likely_prerequisites": ["continuity", "epsilon delta reasoning"]
}
```

### 9.2 Diagnosis API Output

```json
{
  "learner_level": "beginner",
  "missing_prerequisites": ["continuity"],
  "misconception_labels": ["definition confusion"],
  "recommended_teaching_strategy": "example_first"
}
```

### 9.3 Lesson Plan API Output

```json
{
  "start_point": "continuity intuition",
  "sections": [
    "motivation",
    "continuity recap",
    "uniform continuity intuition",
    "formal definition",
    "example",
    "checkpoint"
  ]
}
```

### 9.4 Evaluation API Output

```json
{
  "understanding_summary": {
    "concept": "moderate",
    "formal_definition": "weak",
    "application": "moderate"
  },
  "remaining_gaps": ["formal quantifier interpretation"]
}
```

---

## 10. Suggested Technology Mapping

This section is not mandatory, but useful for implementation planning.

### Input Acquisition

* frontend form
* file upload handler

### Input Understanding

* OCR or vision model
* LLM for structured extraction

### Diagnosis Module

* Python ML pipeline
* scikit-learn or PyTorch
* tabular classifier and/or text classifier

### Lesson Planning

* LLM with strict structured prompt

### Tutoring Delivery

* LLM for tutoring dialogue
* streaming response system

### Whiteboard Rendering

* frontend math rendering with LaTeX
* board event player

### Session State

* backend session store
* Redis or database-backed state manager

### Data Storage

* PostgreSQL or document store

---

## 11. MVP Implementation Order

A recommended order of implementation is:

### Phase 1: Core text pipeline

1. concept text input
2. input understanding from text
3. diagnosis questions
4. lesson planning
5. text-based tutor response

### Phase 2: Interactive lesson flow

6. live session state manager
7. interruption handling
8. final understanding checks

### Phase 3: Visual tutoring

9. whiteboard rendering
10. synchronized explanation flow

### Phase 4: Trained diagnosis model

11. dataset creation
12. feature engineering
13. learner-level and prerequisite-gap model
14. diagnosis model evaluation

### Phase 5: Screenshot support

15. OCR or vision extraction for screenshot input

---

## 12. Testing Strategy

### 12.1 Unit Tests

Each module should be independently testable.

Examples:

* input parser test
* diagnosis feature extraction test
* lesson plan structure test
* interruption resume test

### 12.2 Integration Tests

Test the full flow from concept input to final evaluation.

### 12.3 Educational Quality Tests

Use sample student cases and check:

* whether diagnosis makes sense
* whether lesson starts at the correct level
* whether interruptions are resumed correctly
* whether end-of-lesson checks reflect actual understanding

### 12.4 Diagnosis Model Tests

* cross-validation
* confusion matrix review
* per-class error analysis

---

## 13. Risks and Failure Cases

### 13.1 Mathematical Incorrectness

The tutor may produce wrong explanations.

### 13.2 Overdiagnosis

The system may ask too many questions before teaching.

### 13.3 Weak Resume Behavior

The tutor may lose track after interruptions.

### 13.4 Poor Personalization

The diagnosis model may choose the wrong teaching entry point.

### 13.5 OCR Failure

Math expressions in screenshots may be extracted incorrectly.

### 13.6 Passive Teaching Drift

The tutor may become lecture-like instead of interactive.

---

## 14. Future Enhancements

Future versions may include:

* learner memory across sessions
* persistent skill graph
* spaced repetition review sessions
* exercise generation
* proof-writing coaching
* multi-concept lesson chains
* course-specific tutor modes
* richer handwriting animation
* analytics dashboard for learning progress

---

## 15. Final System Summary

The AI Math Tutor System is an adaptive educational system that teaches one mathematical concept at a time through:

* structured input understanding
* personalized diagnosis
* lesson planning
* live tutoring
* whiteboard-style rendering
* interruption-aware interaction
* understanding evaluation

The most important custom intelligence component is the **Student Diagnosis Module**, which can be trained using machine learning to estimate learner level, prerequisite gaps, and teaching strategy.

This documentation should serve as the foundation for implementation, module decomposition, API planning, and model development.
