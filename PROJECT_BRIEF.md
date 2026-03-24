# Project Brief — AI Math Tutor

**Pillar:** Education
**Stage:** Working MVP (web application)

---

## Problem

University-level mathematics — real analysis, abstract algebra, advanced calculus — is where most students fall behind. Traditional lectures move too fast, textbooks don't adapt to individual knowledge gaps, and private tutors are expensive or unavailable. Students often spend days stuck on a single concept with no personalised way forward. This problem disproportionately affects students from lower-income backgrounds and those studying independently without institutional support.

---

## Target Users

- University and pre-university students encountering rigorous proof-based mathematics for the first time
- Self-learners and working professionals revisiting advanced mathematical topics
- Students in under-resourced institutions without access to academic support centres or private tutors

---

## Solution

**AI Math Tutor** is an adaptive AI tutoring web application that teaches one mathematical concept at a time, end-to-end. The system replicates a private tutoring session entirely on demand:

1. **Input** — Student describes what they want to learn in natural language
2. **Diagnosis** — 4 adaptive questions assess current knowledge, detect misconceptions, and identify prerequisite gaps
3. **Personalised Lesson** — A lesson plan is generated tailored to the student's level and preferred learning style (intuition-first, example-first, formal-definition-first, or proof-based)
4. **Interactive Whiteboard** — The lesson is delivered section by section with real-time LaTeX math rendering and voice narration; the student controls the pace
5. **Interruptions** — Students ask questions at any point; the tutor answers in context and resumes where it left off
6. **Evaluation** — Three post-lesson questions assess comprehension; a personalised summary identifies remaining gaps and the recommended next step

The application is built on FastAPI, LangGraph (AI orchestration), Redis (session state), PostgreSQL (audit trail), and deployed on Fly.io (backend) and Vercel (frontend).

---

## Impact

AI Math Tutor removes the cost and availability barrier to personalised university mathematics tutoring. Any student with internet access receives the same quality of individualised instruction that previously required an expensive human tutor. The system adapts to each student's exact level, directly addressing the STEM education equity gap. It is available 24/7, scales to any number of concurrent students, and improves its diagnosis accuracy over time through a built-in machine learning layer.

---

## Sustainability

The application runs on minimal cloud infrastructure (Fly.io + Vercel + managed Redis and PostgreSQL). LLM inference defaults to cost-efficient fast-tier models. The ML diagnosis model improves automatically with usage, reducing LLM dependency over time. Sustainability paths include institutional licensing to universities and online learning platforms, and a direct student subscription model.

---

## AI Usage

AI tools were used as a development copilot throughout this project — for brainstorming, architecture decisions, code development, testing, and code review. The product itself uses large language models (Groq, Anthropic Claude, OpenAI) to power the tutoring experience at runtime.
