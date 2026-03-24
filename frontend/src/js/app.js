/**
 * app.js - main application controller.
 * Manages diagnosis, lesson delivery, interruptions, and evaluation.
 */

let continueBusy = false;
let interruptBusy = false;

const TOAST_ICONS = { error: '✕', warning: '⚠', success: '✓', info: 'ℹ' };

function showToast(message, type = 'error', duration = 6000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${TOAST_ICONS[type] || TOAST_ICONS.info}</span>
    <span class="toast-body">${String(message).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</span>
    <button class="toast-close" aria-label="Dismiss">&times;</button>
  `;

  const dismiss = () => {
    toast.classList.add('toast-fade-out');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  };

  toast.querySelector('.toast-close').addEventListener('click', dismiss);
  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(dismiss, duration);
  }
}

function showApiError(error) {
  if (error instanceof ApiError) {
    if (error.type === 'offline') {
      showToast('You appear to be offline. Please check your internet connection.', 'warning');
    } else if (error.type === 'connection_error') {
      showToast('Cannot reach the server. Please check your internet connection and try again.', 'warning');
    } else if (error.type === 'not_found') {
      showToast('Session not found. It may have expired — please start a new session.', 'error');
    } else {
      showToast(error.message || 'An unexpected error occurred. Please try again.', 'error');
    }
  } else {
    showToast(error.message || 'An unexpected error occurred. Please try again.', 'error');
  }
}

function show(id) {
  document.getElementById(id)?.classList.remove('hidden');
}

function hide(id) {
  document.getElementById(id)?.classList.add('hidden');
}

function showLoading(message = 'Thinking') {
  const msg = document.getElementById('loading-message');
  if (msg) msg.textContent = message;
  show('loading-overlay');
}

function hideLoading() {
  hide('loading-overlay');
}

function addContinuePrompt(message) {
  const container = document.getElementById('chat-messages');
  // Remove any existing prompt so there's only ever one
  container.querySelectorAll('.continue-prompt').forEach(el => el.remove());
  const el = document.createElement('div');
  el.className = 'continue-prompt';
  el.innerHTML = `<span>${message}</span><span class="cp-arrow">→</span>`;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

function addChatMessage(role, content) {
  const container = document.getElementById('chat-messages');
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble bubble-${role}`;
  bubble.innerHTML = `
    <div class="bubble-label">${role === 'tutor' ? 'Tutor' : 'You'}</div>
    <div>${renderText(content)}</div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  renderMath(bubble);
}

function renderText(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function renderMath(element) {
  if (!window.renderMathInElement) return;
  renderMathInElement(element, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
    ],
    throwOnError: false,
  });
}

function setLoading(buttonId, loading, loadingText = 'Loading...') {
  const button = document.getElementById(buttonId);
  if (!button) return;
  if (loading) {
    button.dataset.origText = button.textContent;
    button.textContent = loadingText;
  } else if (button.dataset.origText) {
    button.textContent = button.dataset.origText;
  }
  button.disabled = loading;
}

function applyLessonControlState() {
  const nextButton = document.getElementById('btn-next-section');
  const interruptButton = document.getElementById('btn-interrupt');
  const interruptInput = document.getElementById('interrupt-input');
  const playing = Whiteboard.isPlaying();

  if (nextButton) {
    nextButton.disabled = continueBusy || interruptBusy || playing;
  }
  if (interruptButton) {
    interruptButton.disabled = interruptBusy;
  }
  if (interruptInput) {
    interruptInput.disabled = interruptBusy;
  }
}

function setContinueBusy(value) {
  continueBusy = value;
  applyLessonControlState();
}

function setInterruptBusy(value) {
  interruptBusy = value;
  applyLessonControlState();
}

function setNextButtonLabel() {
  const button = document.getElementById('btn-next-section');
  if (!button) return;
  button.textContent = Session.isLessonComplete() ? 'Finish lesson >' : 'Continue >';
}

function prepareEvaluation(response) {
  const questions = response.evaluation_questions && response.evaluation_questions.length
    ? response.evaluation_questions
    : [
        `Explain in your own words: ${Session.getTopic()}.`,
        'Can you give a specific example that illustrates the key idea?',
        'What is the most common mistake students make with this topic?',
      ];

  if (response.content) {
    addChatMessage('tutor', response.content);
  }

  Session.setEvaluationQuestions(questions);
  Session.setPhase('evaluating');
  buildEvaluationForm(questions);
  hide('card-lesson');
  show('card-evaluation');
}

async function playTutorPackage(response, options = {}) {
  const deliveryPackage = response.delivery_package;
  if (!deliveryPackage) {
    return { completed: false };
  }

  Session.setActivePackage(deliveryPackage);
  applyLessonControlState();

  const playbackResult = await Whiteboard.playPackage(deliveryPackage);
  applyLessonControlState();

  if (playbackResult?.cancelled) {
    return playbackResult;
  }

  if (options.appendChat !== false && deliveryPackage.transcript) {
    addChatMessage('tutor', deliveryPackage.transcript);
  }

  if (deliveryPackage.section !== 'interruption' && (deliveryPackage.resume_cursor?.audio_offset_ms || 0) === 0) {
    Session.nextSection();
    setNextButtonLabel();
  }

  return playbackResult;
}

async function deliverAdvanceResponse(response) {
  if (response.lesson_sections && !Session.getLessonPlan()) {
    Session.setLessonPlan({ sections: response.lesson_sections });
    setNextButtonLabel();
  }

  if (response.phase === 'done') {
    prepareEvaluation(response);
    return;
  }

  const playbackResult = await playTutorPackage(response);
  Session.setPhase('teaching');

  if (!playbackResult?.cancelled) {
    const isLast = Session.isLessonComplete();
    addContinuePrompt(isLast
      ? 'Section complete — press Continue for the final assessment'
      : 'Section complete — press Continue to move on');
  }
}

document.getElementById('btn-start').addEventListener('click', async () => {
  const inputText = document.getElementById('topic-input').value.trim();
  if (!inputText) return;

  setLoading('btn-start', true);
  showLoading('Setting up your session');
  try {
    const session = await API.createSession(inputText);
    Session.init(session);

    const { questions } = await API.getDiagnosticQuestions(session.session_id);
    Session.setDiagnosticQuestions(questions);
    renderDiagnosticQuestions(questions);

    hide('card-topic');
    show('card-diagnosis');
  } catch (error) {
    showApiError(error);
  } finally {
    hideLoading();
    setLoading('btn-start', false);
  }
});

function renderDiagnosticQuestions(questions) {
  const container = document.getElementById('diagnostic-questions');
  container.innerHTML = '';
  questions.forEach((question, index) => {
    const item = document.createElement('div');
    item.className = 'diag-item';
    item.innerHTML = `
      <label for="diag-${index}">Q${index + 1}. ${question}</label>
      <textarea id="diag-${index}" rows="2" placeholder="Your answer..."></textarea>
    `;
    container.appendChild(item);
  });
}

document.getElementById('btn-submit-diagnosis').addEventListener('click', async () => {
  const questions = Session.getDiagnosticQuestions();
  const answers = questions.map((_, index) => document.getElementById(`diag-${index}`)?.value.trim() || '');

  setLoading('btn-submit-diagnosis', true);
  showLoading('Running diagnosis');
  try {
    const result = await API.submitDiagnosticAnswers(Session.getSessionId(), answers);
    Session.setDiagnosisResult(result);

    Whiteboard.appendSection(
      'diagnosis_summary',
      `**Level:** ${result.learner_level.replace(/_/g, ' ')}\n` +
      `**Strategy:** ${result.recommended_teaching_strategy.replace(/_/g, ' ')}\n` +
      (result.missing_prerequisites.length
        ? `**Gaps detected:** ${result.missing_prerequisites.join(', ')}`
        : '')
    );

    hide('card-diagnosis');
    show('card-lesson');
    addChatMessage(
      'tutor',
      `I have a good sense of where you are. I will start with **${result.recommended_teaching_strategy.replace(/_/g, ' ')}**. Press **Continue** to begin.`
    );
    Session.setPhase('planning');
    applyLessonControlState();
  } catch (error) {
    showApiError(error);
  } finally {
    hideLoading();
    setLoading('btn-submit-diagnosis', false);
  }
});

document.getElementById('btn-next-section').addEventListener('click', async () => {
  setContinueBusy(true);
  showLoading('Preparing next section');
  try {
    const response = await API.advanceSession(Session.getSessionId());
    hideLoading();
    await deliverAdvanceResponse(response);
  } catch (error) {
    showApiError(error);
  } finally {
    hideLoading();
    setContinueBusy(false);
    applyLessonControlState();
  }
});

document.getElementById('btn-interrupt').addEventListener('click', async () => {
  const input = document.getElementById('interrupt-input');
  const question = input.value.trim();
  if (!question) return;

  const playbackCursor = Whiteboard.isPlaying() ? Whiteboard.interruptPlayback() : null;
  addChatMessage('student', question);
  input.value = '';

  setInterruptBusy(true);
  showLoading('Thinking about your question');
  try {
    const response = await API.sendInterruption(Session.getSessionId(), question, playbackCursor || {});
    hideLoading();
    const playbackResult = await playTutorPackage(response);
    if (!playbackResult?.cancelled && response.resume_pending) {
      showLoading('Resuming lesson');
      const resumeResponse = await API.advanceSession(Session.getSessionId());
      hideLoading();
      await deliverAdvanceResponse(resumeResponse);
    }
  } catch (error) {
    showApiError(error);
  } finally {
    hideLoading();
    setInterruptBusy(false);
    applyLessonControlState();
  }
});

document.getElementById('interrupt-input').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    document.getElementById('btn-interrupt').click();
  }
});

function buildEvaluationForm(questions) {
  const container = document.getElementById('evaluation-questions');
  container.innerHTML = '';

  questions.forEach((question, index) => {
    const item = document.createElement('div');
    item.className = 'eval-item';
    item.innerHTML = `
      <p><strong>${index + 1}.</strong> ${renderText(question)}</p>
      <textarea id="eval-${index}" rows="3" placeholder="Your answer..."></textarea>
    `;
    container.appendChild(item);
  });

  renderMath(container);
}

document.getElementById('btn-submit-evaluation').addEventListener('click', async () => {
  const questions = Session.getEvaluationQuestions();
  const answers = questions.map((_, index) => document.getElementById(`eval-${index}`)?.value.trim() || '');

  setLoading('btn-submit-evaluation', true);
  showLoading('Scoring your answers');
  try {
    const result = await API.submitEvaluation(Session.getSessionId(), questions, answers);
    renderResults(result);
    hide('card-evaluation');
    show('card-results');
    Session.setPhase('done');
  } catch (error) {
    showApiError(error);
  } finally {
    hideLoading();
    setLoading('btn-submit-evaluation', false);
  }
});

function renderResults(result) {
  const container = document.getElementById('results-content');
  const summary = result.understanding_summary || {};
  const summaryHtml = Object.entries(summary).map(([key, value]) => `
    <div class="result-row">
      <span class="result-label">${key.replace(/_/g, ' ')}</span>
      <span class="strength-${value}">${value}</span>
    </div>
  `).join('');

  container.innerHTML = `
    ${summaryHtml}
    ${result.remaining_gaps?.length ? `
      <div class="result-row">
        <span class="result-label">Remaining gaps</span>
        <span>${result.remaining_gaps.join(', ')}</span>
      </div>` : ''}
    <div class="result-row">
      <span class="result-label">Recommended next step</span>
      <span>${result.recommended_next_step}</span>
    </div>
  `;
}

document.getElementById('btn-new-session').addEventListener('click', () => {
  location.reload();
});
