/**
 * api.js — thin wrapper around the KS Math Tutor backend API.
 * Set API_BASE to your Fly.io backend URL in production.
 */

const INFERRED_API_HOST = window.location.hostname || 'localhost';
const API_BASE = window.API_BASE || `http://${INFERRED_API_HOST}:8003`;

class ApiError extends Error {
  constructor(message, type = 'server_error', status = 0) {
    super(message);
    this.type = type;   // 'offline' | 'connection_error' | 'not_found' | 'server_error'
    this.status = status;
  }
}

async function apiFetch(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
  } catch (err) {
    if (!navigator.onLine) {
      throw new ApiError('You appear to be offline. Please check your internet connection.', 'offline');
    }
    throw new ApiError(
      'Cannot reach the server. Please check your internet connection or try again shortly.',
      'connection_error'
    );
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail || res.statusText;
    const errorType = body.error || (res.status === 503 ? 'connection_error' : res.status === 404 ? 'not_found' : 'server_error');
    throw new ApiError(detail || `Server error (${res.status})`, errorType, res.status);
  }
  return res.json();
}

const API = {
  resolveUrl(path) {
    if (!path) return null;
    if (/^https?:\/\//i.test(path)) return path;
    return `${API_BASE}${path}`;
  },

  /** POST /api/session/create */
  createSession(inputText, inputType = 'concept_text') {
    return apiFetch('/api/session/create', {
      method: 'POST',
      body: JSON.stringify({ input_text: inputText, input_type: inputType }),
    });
  },

  /** GET /api/session/:id/state */
  getSessionState(sessionId) {
    return apiFetch(`/api/session/${sessionId}/state`);
  },

  /** GET /api/diagnosis/:id/questions */
  getDiagnosticQuestions(sessionId) {
    return apiFetch(`/api/diagnosis/${sessionId}/questions`);
  },

  /** POST /api/diagnosis/submit */
  submitDiagnosticAnswers(sessionId, answers, responseTimesSec = null) {
    return apiFetch('/api/diagnosis/submit', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        answers,
        response_times_sec: responseTimesSec,
      }),
    });
  },

  /** POST /api/session/:id/advance — drive graph one step forward */
  advanceSession(sessionId) {
    return apiFetch(`/api/session/${sessionId}/advance`, { method: 'POST' });
  },

  /** POST /api/session/:id/interrupt */
  sendInterruption(sessionId, questionText, playback = {}) {
    return apiFetch(`/api/session/${sessionId}/interrupt`, {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        question_text: questionText,
        package_id: playback.packageId || null,
        step_id: playback.stepId || null,
        audio_offset_ms: playback.audioOffsetMs || 0,
      }),
    });
  },

  /** POST /api/session/evaluate */
  submitEvaluation(sessionId, questions, answers) {
    return apiFetch('/api/session/evaluate', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, questions, answers }),
    });
  },
};
