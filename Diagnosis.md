# Diagnosis Module Training Documentation

## 1. Document Purpose

This document provides a complete training blueprint for the **Student Diagnosis Module** of the AI Math Tutor System.

The goal of this module is to diagnose a student before or during tutoring and produce the following outputs:

* **learner level**
* **prerequisite gaps**
* **misconception labels**
* **recommended teaching strategy**

This document is focused on the **training and development process** for that diagnosis capability. It is intentionally model-agnostic at this stage. It does not assume whether the final solution will use:

* classical machine learning
* deep learning
* hybrid ML + LLM methods
* rule-based + model-assisted pipelines

The purpose is to help you move from idea to a trainable and testable diagnosis system.

---

## 2. Diagnosis Module Objective

### 2.1 Core Goal

Given:

* a target math concept
* one or more diagnostic questions
* a student’s answers
* optional interaction metadata

The system should predict:

1. the student’s current learner level
2. likely missing prerequisite knowledge
3. probable misconception category or categories
4. the best teaching strategy to begin with

### 2.2 Why This Module Matters

This module is the personalization engine of the tutor.

Without diagnosis, the system teaches all students the same way.
With diagnosis, the system can adapt the starting point, depth, pacing, and style.

### 2.3 Example

Topic: **Uniform continuity**

Student responses show:

* weak understanding of ordinary continuity
* confusion about epsilon-delta quantifiers
* preference for examples over formalism

Diagnosis output may be:

* learner level: beginner-intermediate
* prerequisite gaps: continuity, quantifier reasoning
* misconception labels: definition confusion
* teaching strategy: intuition first, then examples, then formal definition

---

## 3. High-Level Training Roadmap

The recommended process is:

1. define diagnosis outputs clearly
2. define the prediction tasks
3. define the input signals
4. create a labeling scheme
5. design the dataset format
6. collect or generate training data
7. preprocess and engineer features
8. choose baseline modeling approaches
9. train initial models
10. evaluate model quality
11. perform error analysis
12. improve labels, data, and features
13. package the diagnosis pipeline for integration

This document follows that exact order.

---

## 4. Define the Output Space Clearly

Before training any model, you must define exactly what the model should predict.

If the outputs are vague, the training process will fail.

## 4.1 Output 1: Learner Level

This predicts the student’s current level relative to the target topic.

### Example label set

* beginner
* beginner_intermediate
* intermediate
* advanced

### Important Note

Learner level should be **topic-relative**.
A student may be advanced in calculus but beginner in real analysis.

## 4.2 Output 2: Prerequisite Gaps

This predicts what foundational knowledge the student is missing.

### Example label set

* notation
* function basics
* sequence basics
* convergence
* boundedness
* continuity
* epsilon-delta reasoning
* quantifier reasoning
* proof logic
* set language

This output may be **multi-label**, because a student can miss more than one prerequisite.

## 4.3 Output 3: Misconception Labels

This predicts the type of misunderstanding the student currently has.

### Example label set

* wrong implication
* definition confusion
* theorem-definition confusion
* notation confusion
* intuition gap
* proof-step gap
* overgeneralization
* example-only understanding
* quantifier confusion

This may also be **multi-label**.

## 4.4 Output 4: Recommended Teaching Strategy

This predicts the most suitable starting teaching approach.

### Example label set

* intuition_first
* example_first
* formal_definition_first
* proof_first
* prerequisite_micro_lesson_first
* compare_and_contrast_first

This is usually single-label, though you may later support ranked outputs.

---

## 5. Formulate the Machine Learning Tasks

You now convert the diagnosis problem into trainable tasks.

## 5.1 Task A: Learner Level Classification

Input: student diagnostic evidence
Output: learner level label

Task type: multi-class classification

## 5.2 Task B: Prerequisite Gap Detection

Input: student diagnostic evidence + target concept
Output: one or more missing prerequisite labels

Task type: multi-label classification

## 5.3 Task C: Misconception Classification

Input: student answers and behavior signals
Output: one or more misconception labels

Task type: multi-label classification

## 5.4 Task D: Teaching Strategy Recommendation

Input: topic + diagnosis evidence
Output: best teaching strategy label

Task type: multi-class classification

## 5.5 Single Model vs Multiple Models

At this stage, do not force a decision.
The system may later use:

* one model per task
* one shared encoder with multiple output heads
* one hybrid pipeline combining rules and classifiers

Documenting the tasks separately keeps the design flexible.

---

## 6. Define the Inputs to the Diagnosis System

The next step is to define what evidence the diagnosis module can use.

## 6.1 Core Input Categories

The diagnosis module can consume four major kinds of input:

1. **target topic information**
2. **student answers to diagnostic questions**
3. **interaction behavior signals**
4. **derived semantic and structured features**

## 6.2 Topic Information

This includes:

* target concept name
* subject area
* concept difficulty level
* known prerequisites for that concept

### Example

```json
{
  "topic": "uniform continuity",
  "subject_area": "real_analysis",
  "topic_family": "continuity",
  "expected_prerequisites": [
    "functions",
    "continuity",
    "epsilon-delta reasoning"
  ]
}
```

## 6.3 Student Answer Content

This includes raw responses to diagnostic questions.

### Examples

* “It means the sequence is getting close to one number.”
* “Yes, every bounded sequence converges.”
* “I want intuition first.”

These raw responses can later be converted into features.

## 6.4 Interaction Behavior Signals

These include:

* response time
* whether student asked for clarification
* confidence level self-report
* answer revision behavior
* number of hints requested
* number of pauses before answering

These are optional for MVP, but very useful later.

## 6.5 Derived Features

Derived features can come from rules, embeddings, heuristics, or auxiliary models.

Examples:

* correctness score
* semantic similarity to reference answer
* key term coverage
* answer completeness score
* misconception phrase indicators
* informal vs formal expression style

---

## 7. Diagnostic Question Design

The quality of diagnosis depends strongly on the quality of diagnostic questions.

## 7.1 Purpose of Diagnostic Questions

Diagnostic questions are not exam questions.
They are meant to reveal:

* entry level
* missing prerequisites
* misconception patterns
* preferred explanation style

## 7.2 Good Diagnostic Question Properties

A good diagnostic question should be:

* short
* targeted
* interpretable
* easy to label
* linked to a known concept or misconception

## 7.3 Diagnostic Question Categories

### Category A: Definition Check

Example:

* “What does it mean for a sequence to converge?”

### Category B: Distinction Check

Example:

* “Is every bounded sequence convergent?”

### Category C: Prerequisite Recall

Example:

* “Do you already know what continuity at a point means?”

### Category D: Preference Check

Example:

* “Would you like intuition first, examples first, or proof first?”

### Category E: Reasoning Check

Example:

* “Why does choosing epsilon = 1 help in this proof?”

## 7.4 Build a Question Bank

Create a reusable diagnostic question bank for each target topic or topic family.

### Example topic bank: convergence

* What does convergence mean?
* Can a bounded sequence fail to converge?
* What is the difference between boundedness and convergence?
* Would you like an example first or a proof first?

## 7.5 Design Principle

Each question in the bank should ideally map to:

* one or more prerequisite concepts
* one or more misconception types
* one or more teaching strategy implications

---

## 8. Label Schema Design

This is one of the most important parts of the project.

You need a stable annotation scheme.

## 8.1 Why Label Design Matters

Your model can only learn what your labels define.
Poor labels create confusion in training and evaluation.

## 8.2 Learner Level Labeling Guidelines

Use consistent rules.

### Example guideline

* **beginner**: cannot correctly explain core prerequisite ideas
* **beginner_intermediate**: partial intuition but weak formal understanding
* **intermediate**: understands prerequisites but has local confusion
* **advanced**: understands prerequisites and can reason through structure

## 8.3 Prerequisite Gap Labeling Guidelines

Label a prerequisite gap when the answer shows:

* inability to define the concept
* inability to distinguish it from a related concept
* inability to use it in reasoning

### Example

Topic: convergent sequence implies bounded
Student says: “Every bounded sequence converges.”
Possible prerequisite gap labels:

* boundedness vs convergence distinction
* sequence reasoning

## 8.4 Misconception Labeling Guidelines

Define each misconception clearly.

### Example: wrong implication

Definition: student reverses or misstates a one-way implication
Example: “If bounded then convergent.”

### Example: definition confusion

Definition: student cannot state the central concept clearly or mixes it with another idea

### Example: proof-step gap

Definition: student understands the theorem broadly but cannot justify a key proof step

## 8.5 Teaching Strategy Labeling Guidelines

Assign teaching strategy labels based on what would help most.

### Examples

* **intuition_first** when student lacks conceptual picture
* **example_first** when formal language is overwhelming
* **formal_definition_first** when student already has intuition but needs rigor
* **prerequisite_micro_lesson_first** when a required concept is missing

## 8.6 Label Handbook Recommendation

Create a short annotation handbook with:

* label definitions
* examples
* counterexamples
* edge cases

This is extremely important if you later label more data.

---

## 9. Dataset Design

Now you define what each training example looks like.

## 9.1 Recommended Data Unit

A single data point should represent one diagnosis instance.

That means:

* one target topic
* one set of diagnostic questions
* one student’s responses
* one set of labels

## 9.2 Recommended Dataset Fields

```json
{
  "sample_id": "diag_0001",
  "topic": "convergent sequence implies bounded",
  "subject_area": "real_analysis",
  "diagnostic_questions": [
    "What does it mean for a sequence to converge?",
    "Is every bounded sequence convergent?",
    "Would you like intuition first or proof first?"
  ],
  "student_answers": [
    "It approaches a number.",
    "Yes.",
    "Intuition first."
  ],
  "metadata": {
    "response_times_sec": [12, 4, 2],
    "confidence_self_report": "medium",
    "hint_count": 0
  },
  "labels": {
    "learner_level": "beginner_intermediate",
    "prerequisite_gaps": [
      "difference between boundedness and convergence",
      "formal convergence definition"
    ],
    "misconceptions": [
      "wrong implication"
    ],
    "teaching_strategy": "intuition_first"
  }
}
```

## 9.3 Flat Tabular Version

For classical ML, you may flatten the data into columns such as:

* topic
* answer_1_text
* answer_2_text
* answer_3_text
* correct_count
* average_response_time
* confidence_level
* key_term_score
* misconception_phrase_flag
* learner_level_label
* teaching_strategy_label

## 9.4 Sequence Version

For deep learning, you may preserve the question-answer sequence as structured text.

Example serialized format:

* Topic: Uniform continuity
* Q1: What is continuity?
* A1: ...
* Q2: What does uniform mean here?
* A2: ...

This allows later use in transformer-based models.

---

## 10. Data Collection Strategy

This is the hardest practical part.

## 10.1 Recommended Starting Approach

Use a **hybrid data strategy**:

* begin with synthetic labeled examples
* add small real student examples later
* refine labels and question design using error analysis

## 10.2 Option A: Synthetic Dataset

Create diagnosis cases manually.

For each topic:

* write strong student answers
* write partially correct answers
* write common misconceptions
* assign diagnosis labels

### Why this works for MVP

* fast
* controllable
* label quality is easier to manage
* good for competition prototype

## 10.3 Option B: Real Student Data

You can ask actual students a few diagnostic questions and label the responses.

### Advantages

* more realistic language
* captures real ambiguity
* better long-term value

### Challenges

* time-consuming
* requires labeling effort
* may be small and noisy

## 10.4 Option C: Mixed Strategy

Best overall approach:

1. synthetic data first
2. small real dataset second
3. compare how the model behaves on both

## 10.5 Minimum Useful Dataset

Even a small but well-designed dataset is valuable.
For an MVP, the first goal is not huge scale.
The goal is:

* clean label definitions
* useful task framing
* measurable model behavior

---

## 11. Data Preprocessing and Feature Engineering

This stage converts raw diagnosis data into usable model input.

## 11.1 Text Cleaning

For raw answers, you may apply:

* lowercasing if appropriate
* spelling normalization where useful
* whitespace cleanup
* punctuation handling

Be careful not to destroy mathematical meaning.

## 11.2 Structured Feature Engineering

Useful structured features include:

* number of correct answers
* number of partially correct answers
* answer length
* average response time
* preference option chosen
* hint count
* self-reported confidence

## 11.3 Semantic Feature Engineering

Useful semantic features include:

* embedding vectors for answers
* similarity to reference answers
* presence of required mathematical keywords
* presence of misconception phrases
* whether the answer is example-based or definition-based

## 11.4 Auxiliary Scoring Features

You may also compute:

* correctness score per answer
* completeness score per answer
* terminology score
* reasoning clarity score

These scores can come from:

* rules
* heuristics
* an LLM evaluator
* human labeling

## 11.5 Important Design Choice

At first, keep the feature pipeline simple and inspectable.
Do not create a black box too early.

---

## 12. Modeling Options

At this stage, the project remains model-agnostic.
The purpose here is to define reasonable modeling paths.

## 12.1 Option 1: Classical ML on Structured Features

Examples:

* Logistic Regression
* Random Forest
* XGBoost
* Support Vector Machine

### Best for

* small datasets
* interpretable baselines
* tabular features
* competition demos where explanation matters

## 12.2 Option 2: Embedding + Classifier

Pipeline:

* convert student answers into embeddings
* concatenate with structured features
* train classifiers for output tasks

### Best for

* capturing meaning in answers
* moderate complexity
* flexible model experimentation

## 12.3 Option 3: End-to-End Deep Learning

Examples:

* feedforward neural network on engineered features
* transformer-based text classifier
* multi-task neural architecture

### Best for

* larger datasets
* richer text understanding
* future scaling

## 12.4 Option 4: Hybrid LLM-Assisted Diagnosis

Pipeline:

* LLM extracts structured evidence from answers
* downstream ML model predicts final labels

### Best for

* leveraging language understanding
* maintaining structured outputs
* improving small-data performance

## 12.5 Recommended Development Order

Start with:

1. rule-assisted features
2. classical ML baseline
3. embedding-enhanced model
4. deeper models only if justified

---

## 13. Multi-Task vs Separate Training

You have four outputs. There are two main ways to handle them.

## 13.1 Separate Models

Train one model for each output:

* learner level model
* prerequisite gap model
* misconception model
* teaching strategy model

### Pros

* easier debugging
* easier evaluation
* flexible replacement

### Cons

* repeated pipelines
* ignores shared signal unless manually reused

## 13.2 Multi-Task Model

Use a shared representation and predict all outputs together.

### Pros

* shared learning
* more elegant architecture
* potentially better performance if outputs are related

### Cons

* more complex training
* harder debugging
* more difficult with small data

## 13.3 Recommendation

Document both as valid future paths.
Do not force a decision early.
For initial experimentation, separate models are often easier.

---

## 14. Training Procedure

This section describes the step-by-step training workflow.

## 14.1 Step 1: Freeze Label Definitions

Before training, finalize the label taxonomy.

## 14.2 Step 2: Build the First Dataset

Create the first labeled diagnosis dataset.

## 14.3 Step 3: Split the Data

Create:

* training set
* validation set
* test set

If the dataset is very small, use cross-validation carefully.

## 14.4 Step 4: Build a Baseline Feature Pipeline

Start with a simple feature extractor.

## 14.5 Step 5: Train Baseline Models

Train one or more baseline models for each task.

## 14.6 Step 6: Evaluate

Measure performance on the validation or test set.

## 14.7 Step 7: Inspect Errors

Look at wrong predictions manually.

## 14.8 Step 8: Improve

Improve one of:

* labels
* dataset balance
* question design
* features
* model choice

## 14.9 Step 9: Freeze a Prototype Diagnosis Pipeline

Once performance is acceptable, define the diagnosis inference pipeline.

---

## 15. Evaluation Strategy

You should evaluate not only prediction quality, but also whether the diagnosis is useful for tutoring.

## 15.1 Standard Metrics

### For learner level

* accuracy
* macro F1
* confusion matrix

### For prerequisite gaps and misconceptions

* precision
* recall
* F1 score
* exact match or subset metrics if needed

### For teaching strategy

* accuracy
* macro F1

## 15.2 Practical Evaluation Questions

Ask:

* Did the model predict useful prerequisite gaps?
* Did the recommended teaching strategy make pedagogical sense?
* Would a tutor benefit from this diagnosis output?

## 15.3 Human Review Evaluation

It is useful to review predictions manually with a rubric.

Example rubric:

* correct
* mostly useful
* partially useful
* misleading

This is very valuable in an educational AI system.

---

## 16. Error Analysis Framework

Error analysis is where real improvement happens.

## 16.1 Analyze by Label

Check which labels are often confused.

Example:

* beginner_intermediate vs intermediate
* definition confusion vs intuition gap

## 16.2 Analyze by Topic

Some topics may be harder than others.

Example:

* continuity may diagnose well
* compactness may diagnose poorly

## 16.3 Analyze by Answer Style

Check how the model handles:

* short answers
* vague answers
* informal answers
* mathematically correct but nonstandard wording

## 16.4 Analyze by Data Source

Compare synthetic vs real student data.

## 16.5 Common Failure Cases

* answer is correct but phrased simply
* answer is partially correct but overconfident
* misconception and gap overlap
* teaching strategy label is too coarse

---

## 17. Integration Design for Inference

After training, the diagnosis system must work inside the live tutor pipeline.

## 17.1 Inference Flow

1. topic is identified
2. diagnostic questions are selected
3. student answers are collected
4. features are extracted
5. trained model predicts outputs
6. diagnosis summary is returned to lesson planner

## 17.2 Example Inference Output

```json
{
  "learner_level": "beginner_intermediate",
  "prerequisite_gaps": [
    "continuity",
    "quantifier reasoning"
  ],
  "misconceptions": [
    "definition confusion"
  ],
  "recommended_teaching_strategy": "example_first",
  "confidence": {
    "learner_level": 0.79,
    "prerequisite_gaps": 0.71,
    "misconceptions": 0.68,
    "teaching_strategy": 0.75
  }
}
```

## 17.3 Confidence Handling

Store confidence values where possible.
Low confidence can trigger:

* more diagnostic questions
* fallback behavior
* simpler teaching plan

---

## 18. Fallback Strategy

Because educational systems are high-risk for poor personalization, define a fallback path.

## 18.1 When to Use Fallback

Fallback is useful when:

* model confidence is low
* answers are too short
* topic is outside training coverage
* multiple predictions conflict strongly

## 18.2 Fallback Behavior Examples

* ask one extra question
* choose a safer teaching strategy such as intuition first
* recommend a short prerequisite recap
* mark the diagnosis as uncertain internally

---

## 19. Documentation Artifacts You Should Create During Development

To build this module properly, create the following supporting artifacts:

1. diagnosis label handbook
2. diagnostic question bank
3. topic-to-prerequisite map
4. dataset schema document
5. synthetic data generation guide
6. baseline experiment log
7. error analysis log
8. inference API spec

These artifacts will make implementation much easier.

---

## 20. Recommended Development Phases

## Phase 1: Problem Definition

* finalize outputs
* finalize label taxonomy
* define topic scope

## Phase 2: Dataset Design

* create schema
* create question bank
* define annotation rules

## Phase 3: Initial Data Creation

* generate synthetic examples
* label them carefully
* inspect coverage by topic and misconception type

## Phase 4: Baseline Training

* build simple features
* train baseline classifiers
* evaluate results

## Phase 5: Improvement

* refine features
* refine labels
* add embeddings or richer models
* compare model families

## Phase 6: Integration

* package inference pipeline
* connect to lesson planner
* test end-to-end tutoring usefulness

---

## 21. Implementation Notes for MVP

For MVP, keep the diagnosis training goal realistic.

A good MVP diagnosis system does not need to solve everything perfectly.
It only needs to do something useful and demonstrable.

### Strong MVP scope

* 3 to 6 math topics
* 3 to 4 learner level labels
* 6 to 10 prerequisite gap labels
* 5 to 8 misconception labels
* 4 to 6 teaching strategy labels

### Recommended MVP outputs

At minimum, the trained system should predict:

* learner level
* one or more prerequisite gaps
* one teaching strategy

Misconception labels can be added if the dataset quality supports them.

---

## 22. Risks and Challenges

## 22.1 Label Ambiguity

Educational labels are often subjective.

## 22.2 Small Dataset Size

This may limit deep learning performance.

## 22.3 Synthetic Data Bias

Synthetic answers may be cleaner than real student answers.

## 22.4 Overfitting to Question Templates

The model may learn the specific questions instead of true diagnosis patterns.

## 22.5 Output Dependency

Teaching strategy may depend on learner level and gaps, which introduces coupling.

## 22.6 Topic Generalization

A model trained only on real analysis may not generalize to other areas.

---

## 23. Final Recommended Mindset

Do not start by asking:

* “Which model should I use?”

Start by asking:

* “What exactly am I trying to predict?”
* “How will I label it consistently?”
* “What evidence in a student answer reveals that label?”
* “What is the smallest useful diagnosis system I can build first?”

That mindset will help you build a diagnosis module that is scientifically grounded and practically useful.

---

## 24. Final Summary

The Student Diagnosis Module can be developed through a structured process:

1. define outputs clearly
2. define prediction tasks
3. define input evidence
4. design diagnostic questions
5. create a stable label schema
6. design the dataset format
7. collect synthetic and later real data
8. build preprocessing and feature pipelines
9. train baseline models
10. evaluate with both metrics and pedagogical usefulness
11. perform error analysis
12. integrate the trained diagnosis module into the tutoring system

This document is intended to serve as the core implementation guide for building and training the diagnosis component of the AI Math Tutor System.

---

## 25. Current Repo Integration Notes

The current implementation in this repo now follows a practical hybrid path:

* the live diagnosis response still comes from the LLM
* a shadow ML path can run beside it when trained artifacts are present
* diagnosis runs are logged for later training export
* a manual Q-matrix-lite lives in `backend/data/diagnosis_taxonomy/real_analysis.json`

### Q-matrix-lite purpose

This artifact is not a full cognitive diagnosis engine.
It is a structured question-to-skill map used for:

* canonical question ids
* synthetic data generation
* feature engineering
* future migration toward a full CDM if a larger fixed item bank is built

### Repo scaffolding

The current repo contains:

* taxonomy and question mapping utilities
* diagnosis run logging
* synthetic dataset generation
* JSONL export for diagnosis training data
* a TF-IDF plus logistic regression baseline trainer

### Current submission posture

For the submission MVP:

* keep the public diagnosis API stable
* treat ML as shadow and fallback ready
* use the Q-matrix-lite for data design and interpretability
* avoid full DINA or G-DINA implementation until calibrated item response data exists
