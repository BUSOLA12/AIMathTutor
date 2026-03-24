/**
 * session.js — client-side session state.
 * Tracks the current session, diagnosis data, lesson plan, and phase.
 */

const Session = (() => {
  let state = {
    sessionId: null,
    topic: null,
    phase: 'idle',           // idle | diagnosing | planning | teaching | evaluating | done
    diagnosisResult: null,
    lessonPlan: null,
    currentSectionIndex: 0,
    diagnosticQuestions: [],
    evaluationQuestions: [],
    activePackageId: null,
    activeSection: null,
    activeStepId: null,
  };

  function init(sessionResponse) {
    state.sessionId = sessionResponse.session_id;
    state.topic = sessionResponse.topic;
    state.phase = 'diagnosing';
    _updateBadge();
    _updatePhaseIndicator();
  }

  function setDiagnosisResult(result) {
    state.diagnosisResult = result;
    state.phase = 'planning';
    _updatePhaseIndicator();
  }

  function setLessonPlan(plan) {
    state.lessonPlan = plan;
    state.phase = 'teaching';
    state.currentSectionIndex = 0;
    _updatePhaseIndicator();
  }

  function nextSection() {
    state.currentSectionIndex += 1;
  }

  function getCurrentSection() {
    if (!state.lessonPlan) return null;
    return state.lessonPlan.sections[state.currentSectionIndex] || null;
  }

  function isLessonComplete() {
    if (!state.lessonPlan) return false;
    return state.currentSectionIndex >= state.lessonPlan.sections.length;
  }

  function setPhase(phase) {
    state.phase = phase;
    _updatePhaseIndicator();
  }

  function setActivePackage(deliveryPackage) {
    state.activePackageId = deliveryPackage?.package_id || null;
    state.activeSection = deliveryPackage?.section || null;
    state.activeStepId = deliveryPackage?.resume_cursor?.step_id || null;
  }

  function setActiveStep(stepId) {
    state.activeStepId = stepId || null;
  }

  function getSessionId()  { return state.sessionId; }
  function getTopic()      { return state.topic; }
  function getPhase()      { return state.phase; }
  function getDiagnosis()  { return state.diagnosisResult; }
  function getLessonPlan() { return state.lessonPlan; }
  function getActivePackageState() {
    return {
      packageId: state.activePackageId,
      section: state.activeSection,
      stepId: state.activeStepId,
    };
  }

  function _updateBadge() {
    const badge = document.getElementById('session-badge');
    if (badge && state.sessionId) {
      badge.textContent = `Session: ${state.sessionId.slice(0, 8)}`;
      badge.classList.remove('hidden');
    }
  }

  function _updatePhaseIndicator() {
    const el = document.getElementById('phase-indicator');
    if (el) {
      const labels = {
        idle: '—', diagnosing: 'Diagnosing', planning: 'Planning lesson',
        teaching: 'Teaching', evaluating: 'Evaluating', done: 'Complete',
      };
      el.textContent = labels[state.phase] || state.phase;
    }
  }

  return {
    init, setDiagnosisResult, setLessonPlan, nextSection,
    getCurrentSection, isLessonComplete, setPhase,
    getSessionId, getTopic, getPhase, getDiagnosis, getLessonPlan,
    setActivePackage, setActiveStep, getActivePackageState,
    setDiagnosticQuestions(qs) { state.diagnosticQuestions = qs; },
    getDiagnosticQuestions()   { return state.diagnosticQuestions; },
    setEvaluationQuestions(qs) { state.evaluationQuestions = qs; },
    getEvaluationQuestions()   { return state.evaluationQuestions; },
  };
})();
