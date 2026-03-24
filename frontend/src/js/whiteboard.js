/**
 * whiteboard.js - renders live delivery packages onto the whiteboard.
 * Real audio uses backend markers. Browser speech runs as its own
 * audio-first path so visible text cannot outrun narration.
 */

const WB_CHROMIUM_RE = /\b(?:Chrome|Chromium|Edg)\b/i;
const WB_NON_CHROMIUM_RE = /\b(?:OPR|Opera)\b/i;
const WB_SYNC_DEBUG_QUERY = 'syncDebug';
const WB_SYNC_DEBUG_STORAGE_KEY = 'ks.syncDebug';

function wbTokenize(text) {
  return String(text || '').match(/(\$\$[\s\S]*?\$\$|\$[^$]+\$|\s+|[^\s]+)/g) || [];
}

function wbSplitLineChunks(text) {
  const raw = String(text || '');
  if (!raw) {
    return [];
  }

  const newlineChunks = raw.match(/[^\n]+(?:\n+|$)/g);
  if (newlineChunks && newlineChunks.length > 1) {
    return newlineChunks.filter(Boolean);
  }

  const sentenceChunks = raw.match(/[^.!?\n]+[.!?]+(?:\s+|$)|[^.!?\n]+$/g);
  if (sentenceChunks && sentenceChunks.length) {
    return sentenceChunks.filter(Boolean);
  }

  return [raw];
}

function wbBuildRevealUnits(text, revealMode) {
  if (revealMode === 'instant') {
    return [String(text || '')];
  }
  if (revealMode === 'line') {
    const chunks = wbSplitLineChunks(text);
    return chunks.length ? chunks : [String(text || '')];
  }
  const tokens = wbTokenize(text);
  return tokens.length ? tokens : [String(text || '')];
}

function wbBuildTimedRevealPlan(text, revealMode, durationMs) {
  const normalizedMode = revealMode || 'token';
  const units = wbBuildRevealUnits(text, normalizedMode);
  if (normalizedMode === 'instant' || units.length <= 1) {
    return { units, intervalMs: 0 };
  }
  return {
    units,
    intervalMs: Math.max(10, Math.floor(Math.max(1, durationMs) / units.length)),
  };
}

function wbToSpeechFriendlyText(text) {
  return String(text || '')
    .replace(/\$\$([\s\S]*?)\$\$/g, ' $1 ')
    .replace(/\$([^$]+)\$/g, ' $1 ')
    .replace(/\\mathbb\{Z\}/g, 'the integers')
    .replace(/\\mathbb\{R\}/g, 'the real numbers')
    .replace(/\\mathbb\{Q\}/g, 'the rational numbers')
    .replace(/\\mathbb\{N\}/g, 'the natural numbers')
    .replace(/\\mathbb\{C\}/g, 'the complex numbers')
    .replace(/mathbbZ/g, 'the integers')
    .replace(/mathbbR/g, 'the real numbers')
    .replace(/mathbbQ/g, 'the rational numbers')
    .replace(/mathbbN/g, 'the natural numbers')
    .replace(/mathbbC/g, 'the complex numbers')
    .replace(/([A-Za-z])_\{([^}]+)\}\(([^)]+)\)/g, '$1 sub $2 of $3')
    .replace(/([A-Za-z])_([A-Za-z0-9]+)\(([^)]+)\)/g, '$1 sub $2 of $3')
    .replace(/([A-Za-z])_\{([^}]+)\}/g, '$1 sub $2')
    .replace(/([A-Za-z])_([A-Za-z0-9]+)/g, '$1 sub $2')
    .replace(/([A-Za-z])\^\{([^}]+)\}/g, '$1 to the power $2')
    .replace(/([A-Za-z])\^([A-Za-z0-9]+)/g, '$1 to the power $2')
    .replace(/\\/g, ' ')
    .replace(/[{}]/g, ' ')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\n+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function wbNormalizeComparableText(text) {
  return wbToSpeechFriendlyText(text)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function wbNormalizeMathDisplayText(text) {
  let cleaned = String(text || '').trim();
  cleaned = cleaned
    .split('\u000c').join('\\f')
    .split('\u0008').join('\\b')
    .replace(/\r/g, ' ')
    .replace(/\t/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  // Recover a few high-signal LaTeX commands when the leading backslash was
  // swallowed by JSON/control-character damage before the browser saw the step.
  cleaned = cleaned
    .replace(/(^|[^\\A-Za-z])rac\{/g, '$1\\frac{')
    .replace(/(^|[^\\A-Za-z])mathbb\{/g, '$1\\mathbb{')
    .replace(/(^|[^\\A-Za-z])egin\{/g, '$1\\begin{');

  if (!cleaned) {
    return '';
  }
  if (
    (cleaned.startsWith('$$') && cleaned.endsWith('$$'))
    || (cleaned.startsWith('$') && cleaned.endsWith('$'))
  ) {
    return cleaned;
  }
  return `$$${cleaned}$$`;
}

function wbExtractMathExpression(text) {
  const normalized = wbNormalizeMathDisplayText(text);
  if (!normalized) {
    return { normalized, expression: '', displayMode: true };
  }
  if (normalized.startsWith('$$') && normalized.endsWith('$$')) {
    return {
      normalized,
      expression: normalized.slice(2, -2).trim(),
      displayMode: true,
    };
  }
  if (normalized.startsWith('$') && normalized.endsWith('$')) {
    return {
      normalized,
      expression: normalized.slice(1, -1).trim(),
      displayMode: false,
    };
  }
  return { normalized, expression: normalized, displayMode: true };
}

function wbRevealBoundaryText(displayText, charIndex) {
  const safeIndex = Math.max(0, Math.min(String(displayText || '').length, Number(charIndex) || 0));
  return String(displayText || '').slice(0, safeIndex);
}

function wbGetMathCaption(step) {
  const caption = wbToSpeechFriendlyText(step?.spoken_text || '');
  if (!caption) {
    return '';
  }

  const displayComparable = wbNormalizeComparableText(step?.display_text || '');
  const captionComparable = wbNormalizeComparableText(caption);
  return captionComparable && captionComparable !== displayComparable ? caption : '';
}

function wbBuildSpeechRenderPlan(step, options = {}) {
  const displayText = String(step?.display_text || step?.spoken_text || '');
  const speechText = wbToSpeechFriendlyText(
    step?.kind === 'math'
      ? (step?.spoken_text || step?.display_text || '')
      : (step?.spoken_text || step?.display_text || '')
  );
  const revealMode = step?.reveal_mode || 'instant';
  const boundarySupported = Boolean(options.boundarySupported);
  const boundarySafe = ['heading', 'text', 'highlight'].includes(step?.kind || '')
    && wbNormalizeComparableText(displayText) === wbNormalizeComparableText(speechText);

  if (!speechText) {
    return {
      strategy: 'silent',
      displayText,
      speechText,
      revealMode,
      displayChunks: [],
      speechChunks: [],
    };
  }

  if (revealMode === 'instant') {
    return {
      strategy: 'instant',
      displayText,
      speechText,
      revealMode,
      displayChunks: [displayText],
      speechChunks: [speechText],
    };
  }

  if (revealMode === 'token' && boundarySafe && boundarySupported) {
    return {
      strategy: 'boundary',
      displayText,
      speechText,
      revealMode,
      displayChunks: [displayText],
      speechChunks: [speechText],
    };
  }

  const displayChunks = wbSplitLineChunks(displayText);
  const speechChunks = wbSplitLineChunks(speechText);
  const chunkComparable = displayChunks.length > 0
    && displayChunks.length === speechChunks.length
    && displayChunks.every(
      (chunk, index) => wbNormalizeComparableText(chunk) === wbNormalizeComparableText(speechChunks[index])
    );

  if ((revealMode === 'line' || revealMode === 'token') && chunkComparable) {
    return {
      strategy: 'chunked',
      displayText,
      speechText,
      revealMode,
      displayChunks,
      speechChunks,
    };
  }

  return {
    strategy: 'instant',
    displayText,
    speechText,
    revealMode,
    displayChunks: [displayText],
    speechChunks: [speechText],
  };
}

function wbExecuteSpeechPlan(plan, runtime) {
  const {
    createUtterance,
    speak,
    pickVoice,
    onRender = () => {},
    onEvent = () => {},
    onDone = () => {},
    onError = () => {},
  } = runtime;

  let cancelled = false;
  let utteranceStarted = false;
  let firstBoundaryEmitted = false;
  let renderComplete = false;

  const emitUtteranceStart = () => {
    if (!utteranceStarted) {
      utteranceStarted = true;
      onEvent('utterance_start');
    }
  };

  const emitFirstBoundary = detail => {
    if (!firstBoundaryEmitted) {
      firstBoundaryEmitted = true;
      onEvent('first_boundary', detail);
    }
  };

  const emitRenderComplete = () => {
    if (!renderComplete) {
      renderComplete = true;
      onEvent('render_complete');
    }
  };

  const fail = error => {
    if (cancelled) {
      return;
    }
    cancelled = true;
    onError(error);
  };

  const makeUtterance = text => {
    const utterance = createUtterance(text);
    const voice = pickVoice ? pickVoice() : null;
    if (voice) {
      utterance.voice = voice;
    }
    utterance.rate = 0.98;
    utterance.pitch = 1;
    utterance.volume = 1;
    return utterance;
  };

  if (plan.strategy === 'silent') {
    onRender(plan.displayText);
    emitRenderComplete();
    onDone();
    return {
      cancel() {
        cancelled = true;
      },
    };
  }

  const startUtterance = utterance => {
    try {
      speak(utterance);
    } catch (error) {
      fail(error);
    }
  };

  if (plan.strategy === 'instant') {
    const utterance = makeUtterance(plan.speechText);
    utterance.onstart = () => {
      if (cancelled) return;
      emitUtteranceStart();
      onRender(plan.displayText);
      emitRenderComplete();
    };
    utterance.onend = () => {
      if (cancelled) return;
      onEvent('utterance_end');
      onDone();
    };
    utterance.onerror = () => fail(new Error('Speech synthesis failed'));
    startUtterance(utterance);
    return {
      cancel() {
        cancelled = true;
      },
    };
  }

  if (plan.strategy === 'boundary') {
    const utterance = makeUtterance(plan.speechText);
    utterance.onstart = () => {
      if (cancelled) return;
      emitUtteranceStart();
      onRender('');
    };
    utterance.onboundary = event => {
      if (cancelled) return;
      const charIndex = Number(event?.charIndex) || 0;
      emitFirstBoundary({ charIndex });
      onRender(wbRevealBoundaryText(plan.displayText, charIndex));
    };
    utterance.onend = () => {
      if (cancelled) return;
      onRender(plan.displayText);
      emitRenderComplete();
      onEvent('utterance_end');
      onDone();
    };
    utterance.onerror = () => fail(new Error('Speech synthesis failed'));
    startUtterance(utterance);
    return {
      cancel() {
        cancelled = true;
      },
    };
  }

  let renderedText = '';
  const runChunk = index => {
    const utterance = makeUtterance(plan.speechChunks[index] || '');
    utterance.onstart = () => {
      if (cancelled) return;
      emitUtteranceStart();
      renderedText += plan.displayChunks[index] || '';
      onRender(renderedText);
      if (index === plan.speechChunks.length - 1) {
        emitRenderComplete();
      }
    };
    utterance.onend = () => {
      if (cancelled) return;
      if (index >= plan.speechChunks.length - 1) {
        onEvent('utterance_end');
        onDone();
        return;
      }
      runChunk(index + 1);
    };
    utterance.onerror = () => fail(new Error('Speech synthesis failed'));
    startUtterance(utterance);
  };

  runChunk(0);
  return {
    cancel() {
      cancelled = true;
    },
  };
}

const Whiteboard = (() => {
  let playback = null;
  let lastSectionName = null;
  let lastSectionEl = null;

  const boardEl = () => document.getElementById('whiteboard');
  const audioEl = () => document.getElementById('lesson-audio');
  const voiceStatusEl = () => document.getElementById('voice-status');

  function clear() {
    stopPlayback({ removeActiveStep: true, resolveCancelled: true });
    boardEl().innerHTML = '';
    lastSectionName = null;
    lastSectionEl = null;
    _setVoiceStatus('Idle', 'muted');
  }

  function appendSection(sectionName, content) {
    const board = boardEl();
    board.querySelector('.whiteboard-placeholder')?.remove();

    const section = document.createElement('div');
    section.className = 'wb-section';
    section.innerHTML = `
      <div class="wb-section-label">${_formatLabel(sectionName)}</div>
      <div class="wb-package-body">
        <div class="wb-step wb-step-text">${_renderStaticHtml(content)}</div>
      </div>
    `;
    board.appendChild(section);
    _renderMath(section);
    section.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function highlightSection(sectionName) {
    document.querySelectorAll('.wb-section').forEach(el => el.classList.remove('is-live'));
    const sections = document.querySelectorAll('.wb-section');
    const target = [...sections].find(
      el => el.querySelector('.wb-section-label')?.textContent === _formatLabel(sectionName)
    );
    if (target) target.classList.add('is-live');
  }

  async function playPackage(pkg) {
    stopPlayback({ removeActiveStep: true, resolveCancelled: true });

    const sectionEl = _ensureSection(pkg);
    const bodyEl = sectionEl.querySelector('.wb-package-body');
    const startOffsetMs = pkg.resume_cursor?.audio_offset_ms || 0;
    const markers = _buildMarkers(pkg);
    const stepLookup = new Map((pkg.steps || []).map(step => [step.step_id, step]));
    const markerLookup = new Map(markers.map(marker => [marker.name, marker.time_ms]));
    const markerIndexLookup = new Map(markers.map((marker, index) => [marker.name, index]));
    const stepIndexLookup = new Map((pkg.steps || []).map((step, index) => [step.step_id, index]));

    return new Promise(async resolve => {
      playback = {
        packageId: pkg.package_id,
        section: pkg.section,
        sectionEl,
        bodyEl,
        steps: pkg.steps || [],
        markers,
        stepLookup,
        markerLookup,
        markerIndexLookup,
        stepIndexLookup,
        nextMarkerIndex: 0,
        sequenceIndex: 0,
        activeStep: null,
        renderedSteps: new Map(),
        startOffsetMs,
        audioDurationMs: pkg.audio_duration_ms || 0,
        audio: null,
        audioProvider: pkg.audio_provider || null,
        rafId: null,
        pendingAnimations: 0,
        pendingSpeechCount: 0,
        audioEnded: false,
        mode: _shouldUseAudio(pkg) ? 'audio-marker' : (_canUseBrowserSpeech() ? 'browser-speech' : 'timed'),
        usingAudio: false,
        usingBrowserSpeech: false,
        speechCancelled: false,
        speechExecution: null,
        timeoutIds: new Set(),
        startedAt: performance.now(),
        resolve,
        finished: false,
      };

      _ensureSyncDebugStore();
      _recordSyncEvent(playback, null, 'playback_start', {
        audioProvider: playback.audioProvider,
        stepCount: playback.steps.length,
      });

      _setVoiceStatus(_shouldUseAudio(pkg) ? 'Syncing voice' : 'Preparing browser voice', 'loading');
      highlightSection(pkg.section);

      if (_shouldUseAudio(pkg)) {
        await _startAudioMarkerPlayback(playback, pkg);
        return;
      }

      _startFallbackPlayback(playback);
    });
  }

  function interruptPlayback() {
    if (!playback) {
      return null;
    }

    const activePlayback = playback;
    const resumeStepId = _getResumeStepId(activePlayback);
    const resumeOffsetMs = _getResumeOffset(activePlayback, resumeStepId);

    stopPlayback({ removeActiveStep: true, resolveCancelled: true, nextStatus: 'Paused' });

    if (!resumeStepId) {
      return null;
    }

    return {
      packageId: activePlayback.packageId,
      stepId: resumeStepId,
      audioOffsetMs: resumeOffsetMs,
    };
  }

  function isPlaying() {
    return Boolean(playback);
  }

  function stopPlayback(options = {}) {
    if (!playback) {
      return;
    }

    const {
      removeActiveStep = false,
      resolveCancelled = false,
      nextStatus = 'Idle',
      nextMode = nextStatus === 'Idle' || nextStatus === 'Paused' ? 'muted' : 'loading',
    } = options;

    const current = playback;
    playback = null;

    if (current.rafId) {
      cancelAnimationFrame(current.rafId);
    }
    for (const timeoutId of current.timeoutIds) {
      clearTimeout(timeoutId);
    }
    current.timeoutIds.clear();

    if (current.audio) {
      current.audio.pause();
      current.audio.onended = null;
      current.audio.onerror = null;
    }
    if (current.usingBrowserSpeech && typeof window !== 'undefined' && window.speechSynthesis) {
      current.speechCancelled = true;
      current.speechExecution?.cancel?.();
      window.speechSynthesis.cancel();
    }
    if (removeActiveStep && current.activeStep && !current.activeStep.finalized && current.activeStep.el) {
      current.activeStep.el.remove();
      current.renderedSteps.delete(current.activeStep.stepId);
    }
    if (resolveCancelled && !current.finished) {
      current.finished = true;
      current.resolve({ cancelled: true, packageId: current.packageId });
    }

    _recordSyncEvent(current, current.activeStep?.stepId || null, 'playback_stop', {
      nextStatus,
    });
    _setVoiceStatus(nextStatus, nextMode);
  }

  async function _startAudioMarkerPlayback(state, pkg) {
    state.mode = 'audio-marker';
    state.usingAudio = true;

    const audio = audioEl();
    state.audio = audio;
    audio.pause();
    audio.onended = null;
    audio.onerror = null;
    audio.src = API.resolveUrl(pkg.audio_url);

    try {
      await _waitForAudio(audio);
      audio.currentTime = state.startOffsetMs / 1000;
      audio.onended = () => {
        if (!playback || playback.packageId !== state.packageId) {
          return;
        }
        state.audioEnded = true;
        _maybeFinishAudioPlayback(state);
      };
      audio.onerror = () => {
        if (!playback || playback.packageId !== state.packageId) {
          return;
        }
        _fallbackFromAudio(state);
      };

      await audio.play();
      _setVoiceStatus('Narrating live', 'live');
      _tickAudioPlayback();
    } catch (_error) {
      _fallbackFromAudio(state);
    }
  }

  function _fallbackFromAudio(state) {
    if (!playback || playback.packageId !== state.packageId || state.finished) {
      return;
    }

    if (state.rafId) {
      cancelAnimationFrame(state.rafId);
      state.rafId = null;
    }
    if (state.audio) {
      state.audio.pause();
      state.audio.onended = null;
      state.audio.onerror = null;
      state.audio = null;
    }

    const resumeStepId = _getResumeStepId(state);
    if (state.activeStep && !state.activeStep.finalized && state.activeStep.el) {
      state.activeStep.el.remove();
      state.renderedSteps.delete(state.activeStep.stepId);
    }

    state.usingAudio = false;
    state.audioEnded = false;
    state.startedAt = performance.now();
    state.nextMarkerIndex = 0;
    state.sequenceIndex = state.stepIndexLookup.get(resumeStepId) || 0;
    state.activeStep = null;

    _recordSyncEvent(state, resumeStepId, 'audio_fallback', {});
    _startFallbackPlayback(state);
  }

  function _startFallbackPlayback(state) {
    if (_enableBrowserSpeech(state)) {
      state.mode = 'browser-speech';
      state.sequenceIndex = Math.max(0, state.sequenceIndex || 0);
      _playNextSequentialStep(state);
      return;
    }

    state.mode = 'timed';
    _setVoiceStatus('Timed playback', 'muted');
    _playNextSequentialStep(state);
  }

  function _tickAudioPlayback() {
    if (!playback || playback.mode !== 'audio-marker') return;

    const elapsedMs = _elapsedMs(playback);
    while (
      playback.nextMarkerIndex < playback.markers.length &&
      playback.markers[playback.nextMarkerIndex].time_ms <= elapsedMs + 20
    ) {
      const markerIndex = playback.nextMarkerIndex;
      const marker = playback.markers[markerIndex];
      const nextMarker = playback.markers[markerIndex + 1];
      const step = playback.stepLookup.get(marker.name);
      if (step) {
        _renderAudioStep(playback, step, marker, nextMarker);
      }
      playback.nextMarkerIndex += 1;
    }

    _maybeFinishAudioPlayback(playback);
    if (!playback || playback.finished || playback.mode !== 'audio-marker') {
      return;
    }

    playback.rafId = requestAnimationFrame(_tickAudioPlayback);
  }

  function _renderAudioStep(state, step, marker, nextMarker) {
    const nextTimeMs = nextMarker ? nextMarker.time_ms : state.audioDurationMs;
    const durationMs = Math.max(500, nextTimeMs - marker.time_ms);

    state.activeStep = {
      stepId: step.step_id,
      startMarkerMs: marker.time_ms,
      finalized: false,
      el: null,
    };
    _setActiveStep(step.step_id);

    if (step.kind === 'pause') {
      state.activeStep.finalized = true;
      _maybeFinishAudioPlayback(state);
      return;
    }

    if (step.kind === 'highlight') {
      _applyHighlightTarget(state, step);
      const noteText = _getHighlightNoteText(step);
      if (!noteText) {
        state.activeStep.finalized = true;
        _maybeFinishAudioPlayback(state);
        return;
      }
      const noteEl = _appendHighlightNoteElement(state, step);
      state.activeStep.el = noteEl;
      _runTimedReveal(state, step, noteEl, durationMs);
      return;
    }

    const stepEl = _appendStepElement(state, step);
    state.activeStep.el = stepEl;

    if (step.kind === 'math') {
      _runTimedMathReveal(state, step, stepEl, durationMs);
      return;
    }

    _runTimedReveal(state, step, stepEl, durationMs);
  }

  function _playNextSequentialStep(state) {
    if (!playback || playback.packageId !== state.packageId || state.finished) {
      return;
    }

    if (state.sequenceIndex >= state.steps.length) {
      _finishSequentialPlayback(state);
      return;
    }

    const step = state.steps[state.sequenceIndex];
    state.sequenceIndex += 1;
    state.activeStep = {
      stepId: step.step_id,
      startMarkerMs: state.markerLookup.get(step.step_id) || 0,
      finalized: false,
      el: null,
    };
    _setActiveStep(step.step_id);

    if (step.kind === 'pause') {
      const waitMs = _getSequentialStepDuration(state, step);
      _schedule(state, () => _completeSequentialStep(state, step), waitMs);
      return;
    }

    if (step.kind === 'highlight') {
      _applyHighlightTarget(state, step);
      const noteText = _getHighlightNoteText(step);
      if (!noteText) {
        _completeSequentialStep(state, step);
        return;
      }

      const noteEl = _appendHighlightNoteElement(state, step);
      state.activeStep.el = noteEl;
      if (state.mode === 'browser-speech' && wbToSpeechFriendlyText(step.spoken_text || step.display_text)) {
        _runBrowserSpeechStep(state, step, noteEl);
        return;
      }
      _runTimedReveal(state, step, noteEl, _getSequentialStepDuration(state, step), () => {
        _completeSequentialStep(state, step);
      });
      return;
    }

    const stepEl = _appendStepElement(state, step);
    state.activeStep.el = stepEl;

    if (step.kind === 'math') {
      if (state.mode === 'browser-speech') {
        _runBrowserSpeechMathStep(state, step, stepEl);
        return;
      }
      _runTimedMathReveal(state, step, stepEl, _getSequentialStepDuration(state, step), () => {
        _completeSequentialStep(state, step);
      });
      return;
    }

    if (state.mode === 'browser-speech') {
      _runBrowserSpeechStep(state, step, stepEl);
      return;
    }

    _runTimedReveal(state, step, stepEl, _getSequentialStepDuration(state, step), () => {
      _completeSequentialStep(state, step);
    });
  }

  function _runBrowserSpeechMathStep(state, step, stepEl) {
    const captionText = wbGetMathCaption(step);
    _renderMathStep(stepEl, step, { captionText: '' });

    if (!captionText) {
      const instantMathStep = {
        kind: 'text',
        display_text: step.spoken_text || step.display_text || '',
        spoken_text: step.spoken_text || step.display_text || '',
        reveal_mode: 'instant',
      };
      _runBrowserSpeechStep(state, instantMathStep, stepEl, {
        onRender: () => {
          _renderMathStep(stepEl, step, { captionText: '' });
        },
        onRenderComplete: () => {
          _renderMathStep(stepEl, step, { captionText: '' });
        },
        onDone: () => {
          if (!playback || playback.packageId !== state.packageId || state.speechCancelled) {
            return;
          }
          state.pendingSpeechCount = 0;
          state.speechExecution = null;
          _completeSequentialStep(state, step);
        },
      });
      return;
    }

    const captionStep = {
      kind: 'text',
      display_text: captionText,
      spoken_text: step.spoken_text || captionText,
      reveal_mode: 'token',
    };

    _runBrowserSpeechStep(state, captionStep, stepEl, {
      onRender: renderedCaption => {
        _renderMathStep(stepEl, step, {
          captionText: renderedCaption,
          showCaptionSlot: true,
        });
      },
      onRenderComplete: () => {
        _renderMathStep(stepEl, step, {
          captionText,
          showCaptionSlot: true,
        });
      },
      onDone: () => {
        if (!playback || playback.packageId !== state.packageId || state.speechCancelled) {
          return;
        }
        state.pendingSpeechCount = 0;
        state.speechExecution = null;
        _completeSequentialStep(state, step);
      },
    });
  }

  function _runBrowserSpeechStep(state, step, stepEl, options = {}) {
    const planStep = options.planStep || step;
    const plan = wbBuildSpeechRenderPlan(planStep, { boundarySupported: _supportsBoundarySync() });
    const shouldShowWritingCursor = plan.strategy === 'boundary' || plan.strategy === 'chunked';
    if (stepEl && shouldShowWritingCursor) {
      stepEl.classList.add('wb-step-writing');
    }

    state.pendingSpeechCount = 1;
    state.speechExecution = wbExecuteSpeechPlan(plan, {
      createUtterance(text) {
        return new SpeechSynthesisUtterance(text);
      },
      speak(utterance) {
        window.speechSynthesis.speak(utterance);
      },
      pickVoice: _pickSpeechVoice,
      onRender: renderedText => {
        if (!playback || playback.packageId !== state.packageId || state.speechCancelled) {
          return;
        }
        if (options.onRender) {
          options.onRender(renderedText);
        } else if (stepEl) {
          _renderTextStep(stepEl, renderedText);
          if (renderedText === plan.displayText) {
            stepEl.classList.remove('wb-step-writing');
          }
        }
      },
      onEvent: (eventType, detail = {}) => {
        if (!playback || playback.packageId !== state.packageId || state.speechCancelled) {
          return;
        }
        if (eventType === 'render_complete' && stepEl) {
          stepEl.classList.remove('wb-step-writing');
        }
        if (eventType === 'render_complete' && options.onRenderComplete) {
          options.onRenderComplete();
        }
        _recordSyncEvent(state, step.step_id, eventType, detail);
      },
      onDone: () => {
        if (!playback || playback.packageId !== state.packageId || state.speechCancelled) {
          return;
        }
        if (options.onDone) {
          options.onDone();
          return;
        }
        state.pendingSpeechCount = 0;
        state.speechExecution = null;
        _completeSequentialStep(state, step);
      },
      onError: () => {
        if (!playback || playback.packageId !== state.packageId) {
          return;
        }
        state.pendingSpeechCount = 0;
        state.speechExecution = null;
        _fallbackFromBrowserSpeech(state, step.step_id);
      },
    });
  }

  function _fallbackFromBrowserSpeech(state, stepId) {
    if (!playback || playback.packageId !== state.packageId || state.finished) {
      return;
    }

    state.speechCancelled = true;
    state.speechExecution?.cancel?.();
    state.speechExecution = null;
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    state.usingBrowserSpeech = false;
    state.pendingSpeechCount = 0;
    state.mode = 'timed';

    if (state.activeStep && !state.activeStep.finalized && state.activeStep.el) {
      state.activeStep.el.remove();
      state.renderedSteps.delete(state.activeStep.stepId);
    }

    state.activeStep = null;
    state.sequenceIndex = state.stepIndexLookup.get(stepId) || 0;
    _recordSyncEvent(state, stepId, 'speech_fallback', {});
    _setVoiceStatus('Timed playback', 'muted');
    _playNextSequentialStep(state);
  }

  function _completeSequentialStep(state, step) {
    if (!playback || playback.packageId !== state.packageId || state.finished) {
      return;
    }
    if (state.activeStep && state.activeStep.stepId === step.step_id) {
      state.activeStep.finalized = true;
    }
    _playNextSequentialStep(state);
  }

  function _finishSequentialPlayback(state) {
    if (!playback || playback.packageId !== state.packageId || state.finished) {
      return;
    }
    state.finished = true;
    if (state.sectionEl) {
      state.sectionEl.classList.remove('is-live');
    }
    _recordSyncEvent(state, null, 'playback_complete', { mode: state.mode });
    _setVoiceStatus('Idle', 'muted');
    playback = null;
    state.resolve({ completed: true, packageId: state.packageId });
  }

  function _runTimedMathReveal(state, step, stepEl, durationMs, onComplete) {
    const captionText = wbGetMathCaption(step);
    _renderMathStep(stepEl, step, { captionText: '' });

    if (!captionText) {
      if (state.activeStep && state.activeStep.stepId === step.step_id) {
        state.activeStep.finalized = true;
      }
      if (onComplete) {
        onComplete();
      } else {
        _maybeFinishAudioPlayback(state);
      }
      return;
    }

    const captionStep = {
      ...step,
      kind: 'text',
      display_text: captionText,
      spoken_text: step.spoken_text || captionText,
      reveal_mode: 'token',
    };

    _runTimedReveal(
      state,
      captionStep,
      stepEl,
      durationMs,
      onComplete,
      renderedCaption => {
        _renderMathStep(stepEl, step, {
          captionText: renderedCaption,
          showCaptionSlot: true,
        });
      }
    );
  }

  function _runTimedReveal(state, step, stepEl, durationMs, onComplete, renderFn = null) {
    const text = _getRevealDisplayText(step);
    const plan = wbBuildTimedRevealPlan(text, step.reveal_mode || 'token', durationMs);

    if (plan.units.length <= 1 || step.reveal_mode === 'instant') {
      if (renderFn) {
        renderFn(text);
      } else {
        _renderTextStep(stepEl, text);
      }
      if (state.activeStep && state.activeStep.stepId === step.step_id) {
        state.activeStep.finalized = true;
      }
      if (onComplete) {
        onComplete();
      } else {
        _maybeFinishAudioPlayback(state);
      }
      return;
    }

    let index = 0;
    state.pendingAnimations += 1;
    stepEl.classList.add('wb-step-writing');

    const advanceUnit = () => {
      if (!playback || playback.packageId !== state.packageId) {
        return;
      }

      if (state.activeStep && state.activeStep.stepId !== step.step_id) {
        index = plan.units.length;
      } else {
        index += 1;
      }

      const renderedText = plan.units.slice(0, index).join('');
      if (renderFn) {
        renderFn(renderedText);
      } else {
        _renderTextStep(stepEl, renderedText);
      }

      if (index < plan.units.length) {
        _schedule(state, advanceUnit, plan.intervalMs);
        return;
      }

      stepEl.classList.remove('wb-step-writing');
      if (state.activeStep && state.activeStep.stepId === step.step_id) {
        state.activeStep.finalized = true;
      }
      state.pendingAnimations = Math.max(0, state.pendingAnimations - 1);
      if (onComplete) {
        onComplete();
      } else {
        _maybeFinishAudioPlayback(state);
      }
    };

    _schedule(state, advanceUnit, 0);
  }

  function _appendStepElement(state, step) {
    const stepEl = document.createElement('div');
    stepEl.className = `wb-step wb-step-${step.kind === 'math' ? 'math' : step.kind}`;
    state.bodyEl.appendChild(stepEl);
    state.bodyEl.scrollTop = state.bodyEl.scrollHeight;
    state.renderedSteps.set(step.step_id, stepEl);
    return stepEl;
  }

  function _appendHighlightNoteElement(state, step) {
    const noteEl = document.createElement('div');
    noteEl.className = 'wb-step wb-step-highlight-note';
    state.bodyEl.appendChild(noteEl);
    state.bodyEl.scrollTop = state.bodyEl.scrollHeight;
    state.renderedSteps.set(step.step_id, noteEl);
    return noteEl;
  }

  function _getRevealDisplayText(step) {
    if (step.kind === 'highlight') {
      return _getHighlightNoteText(step);
    }
    return step.display_text || step.spoken_text || '';
  }

  function _getHighlightNoteText(step) {
    return String(step.display_text || step.spoken_text || '').trim();
  }

  function _renderTextStep(stepEl, text) {
    stepEl.innerHTML = _renderStaticHtml(text);
    _renderMath(stepEl);
    _keepScrolledToBottom(stepEl.parentElement);
  }

  function _renderMathStep(stepEl, step, options = {}) {
    const mathCaption = options.captionText ?? wbGetMathCaption(step);
    const showCaptionSlot = options.showCaptionSlot || Boolean(mathCaption);
    stepEl.innerHTML = `
      <div class="wb-step-math-formula"></div>
      ${showCaptionSlot ? `<div class="wb-step-math-caption">${_renderStaticHtml(mathCaption)}</div>` : ''}
    `;
    _renderMathFormula(stepEl.querySelector('.wb-step-math-formula'), step.display_text || '');
    _keepScrolledToBottom(stepEl.parentElement);
  }

  function _renderMathFormula(formulaEl, text) {
    if (!formulaEl) {
      return;
    }

    const { expression, displayMode } = wbExtractMathExpression(text);
    if (!expression) {
      formulaEl.textContent = '';
      return;
    }

    if (window.katex?.render) {
      try {
        window.katex.render(expression, formulaEl, {
          displayMode,
          throwOnError: true,
        });
        formulaEl.classList.remove('wb-step-math-fallback');
        return;
      } catch (_error) {
        formulaEl.classList.add('wb-step-math-fallback');
        formulaEl.innerHTML = _renderStaticHtml('Unable to render formula.');
        return;
      }
    }

    formulaEl.innerHTML = _renderStaticHtml(text);
    _renderMath(formulaEl);
  }

  function _applyHighlightTarget(state, step) {
    const targetId = step.target || [...state.renderedSteps.keys()].pop();
    if (targetId && state.renderedSteps.has(targetId)) {
      state.renderedSteps.get(targetId).classList.add('wb-step-highlighted');
    }
  }

  function _maybeFinishAudioPlayback(state) {
    if (!playback || playback.packageId !== state.packageId || state.finished) {
      return;
    }

    const allMarkersFired = state.nextMarkerIndex >= state.markers.length;
    const timelineFinished = state.audioEnded;

    if (allMarkersFired && state.pendingAnimations === 0 && timelineFinished) {
      state.finished = true;
      if (state.sectionEl) {
        state.sectionEl.classList.remove('is-live');
      }
      _recordSyncEvent(state, null, 'playback_complete', { mode: state.mode });
      _setVoiceStatus('Idle', 'muted');
      playback = null;
      state.resolve({ completed: true, packageId: state.packageId });
    }
  }

  function _elapsedMs(state) {
    if (state.usingAudio && state.audio) {
      return Math.max(0, (state.audio.currentTime * 1000) - state.startOffsetMs);
    }
    return Math.max(0, performance.now() - state.startedAt);
  }

  function _ensureSection(pkg) {
    const board = boardEl();
    board.querySelector('.whiteboard-placeholder')?.remove();

    if (
      pkg.resume_cursor?.audio_offset_ms > 0 &&
      lastSectionEl &&
      lastSectionName === pkg.section
    ) {
      lastSectionEl.classList.add('is-live');
      return lastSectionEl;
    }

    const section = document.createElement('div');
    section.className = 'wb-section is-live';
    section.dataset.section = pkg.section;
    section.innerHTML = `
      <div class="wb-section-label">${_formatLabel(pkg.section)}</div>
      <div class="wb-package-body"></div>
    `;
    board.appendChild(section);
    section.scrollIntoView({ behavior: 'smooth', block: 'end' });

    lastSectionName = pkg.section;
    lastSectionEl = section;
    return section;
  }

  function _buildMarkers(pkg) {
    const markers = [...(pkg.markers || [])].sort((a, b) => a.time_ms - b.time_ms);
    if (markers.length) {
      return markers;
    }
    return (pkg.steps || []).map((step, index) => ({
      name: step.step_id,
      time_ms: index * 900,
    }));
  }

  function _getSequentialStepDuration(state, step) {
    const markerIndex = state.markerIndexLookup.get(step.step_id);
    const marker = markerIndex != null ? state.markers[markerIndex] : null;
    const nextMarker = markerIndex != null ? state.markers[markerIndex + 1] : null;
    if (marker) {
      const nextTimeMs = nextMarker ? nextMarker.time_ms : state.audioDurationMs;
      return Math.max(500, nextTimeMs - marker.time_ms);
    }
    return 900;
  }

  function _getResumeStepId(state) {
    if (state.activeStep && !state.activeStep.finalized) {
      return state.activeStep.stepId;
    }
    if (state.mode === 'audio-marker' && state.nextMarkerIndex < state.markers.length) {
      return state.markers[state.nextMarkerIndex].name;
    }
    if (state.sequenceIndex < state.steps.length) {
      return state.steps[state.sequenceIndex].step_id;
    }
    return null;
  }

  function _getResumeOffset(state, stepId) {
    if (!stepId) {
      return Math.round(state.startOffsetMs + _elapsedMs(state));
    }
    const relativeMarkerMs = state.markerLookup.get(stepId) || 0;
    return state.startOffsetMs + relativeMarkerMs;
  }

  function _renderStaticHtml(text) {
    return _escapeHtml(text)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  function _renderPlainHtml(text) {
    return _escapeHtml(text).replace(/\n/g, '<br>');
  }

  function _escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function _renderMath(element) {
    if (!window.renderMathInElement || !element) return;
    renderMathInElement(element, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
      ],
      throwOnError: false,
    });
  }

  function _waitForAudio(audio) {
    if (audio.readyState >= 1) {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const cleanup = () => {
        audio.removeEventListener('loadedmetadata', onReady);
        audio.removeEventListener('error', onError);
      };
      const onReady = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(new Error('Audio metadata failed to load'));
      };
      audio.addEventListener('loadedmetadata', onReady, { once: true });
      audio.addEventListener('error', onError, { once: true });
    });
  }

  function _shouldUseAudio(pkg) {
    return Boolean(pkg.audio_url && pkg.audio_provider !== 'mock');
  }

  function _enableBrowserSpeech(state) {
    if (!_canUseBrowserSpeech()) {
      state.usingBrowserSpeech = false;
      return false;
    }

    try {
      state.usingBrowserSpeech = true;
      state.pendingSpeechCount = 0;
      state.speechCancelled = false;
      window.speechSynthesis.cancel();
      _setVoiceStatus('Browser voice', 'live');
      return true;
    } catch (_error) {
      state.usingBrowserSpeech = false;
      state.pendingSpeechCount = 0;
      return false;
    }
  }

  function _canUseBrowserSpeech() {
    return Boolean(window.speechSynthesis && typeof SpeechSynthesisUtterance !== 'undefined');
  }

  function _supportsBoundarySync() {
    const userAgent = typeof navigator !== 'undefined' ? (navigator.userAgent || '') : '';
    return _canUseBrowserSpeech()
      && WB_CHROMIUM_RE.test(userAgent)
      && !WB_NON_CHROMIUM_RE.test(userAgent);
  }

  function _pickSpeechVoice() {
    if (!_canUseBrowserSpeech()) {
      return null;
    }

    const voices = window.speechSynthesis.getVoices() || [];
    return (
      voices.find(voice => /^en(-|_)/i.test(voice.lang || '') && voice.default) ||
      voices.find(voice => /^en(-|_)/i.test(voice.lang || '')) ||
      voices.find(voice => voice.default) ||
      voices[0] ||
      null
    );
  }

  function _setVoiceStatus(text, mode = 'muted') {
    const el = voiceStatusEl();
    if (!el) return;
    el.textContent = text;
    el.classList.remove('is-loading', 'is-muted');
    if (mode === 'loading') el.classList.add('is-loading');
    if (mode === 'muted') el.classList.add('is-muted');
  }

  function _formatLabel(name) {
    return String(name || '')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  function _keepScrolledToBottom(body) {
    if (!body) {
      return;
    }
    const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 120;
    if (atBottom) {
      body.scrollTop = body.scrollHeight;
    }
  }

  function _schedule(state, fn, delayMs) {
    const timeoutId = setTimeout(() => {
      state.timeoutIds.delete(timeoutId);
      fn();
    }, delayMs);
    state.timeoutIds.add(timeoutId);
    return timeoutId;
  }

  function _setActiveStep(stepId) {
    if (typeof Session !== 'undefined' && Session?.setActiveStep) {
      Session.setActiveStep(stepId);
    }
  }

  function _isSyncDebugEnabled() {
    if (typeof window === 'undefined') {
      return false;
    }

    if (window.KS_SYNC_DEBUG === true) {
      return true;
    }

    try {
      if (window.location?.search) {
        const params = new URLSearchParams(window.location.search);
        if (params.get(WB_SYNC_DEBUG_QUERY) === '1') {
          return true;
        }
      }
      if (window.localStorage?.getItem(WB_SYNC_DEBUG_STORAGE_KEY) === '1') {
        return true;
      }
    } catch (_error) {
      return false;
    }

    return false;
  }

  function _ensureSyncDebugStore() {
    if (typeof window === 'undefined') {
      return null;
    }

    if (!window.__KS_SYNC_DEBUG__) {
      const store = {
        enabled: _isSyncDebugEnabled(),
        events: [],
        clear() {
          this.events.length = 0;
        },
      };
      window.__KS_SYNC_DEBUG__ = store;
    } else {
      window.__KS_SYNC_DEBUG__.enabled = _isSyncDebugEnabled();
      if (!Array.isArray(window.__KS_SYNC_DEBUG__.events)) {
        window.__KS_SYNC_DEBUG__.events = [];
      }
    }
    return window.__KS_SYNC_DEBUG__;
  }

  function _recordSyncEvent(state, stepId, eventType, extra = {}) {
    const store = _ensureSyncDebugStore();
    if (!store?.enabled) {
      return;
    }

    store.events.push({
      packageId: state.packageId,
      section: state.section,
      stepId,
      mode: state.mode,
      eventType,
      offsetMs: Math.round(_elapsedMs(state)),
      ...extra,
    });
  }

  return {
    clear,
    appendSection,
    highlightSection,
    playPackage,
    interruptPlayback,
    isPlaying,
    stopPlayback,
  };
})();

const WhiteboardTestUtils = {
  tokenize: wbTokenize,
  splitLineChunks: wbSplitLineChunks,
  buildRevealUnits: wbBuildRevealUnits,
  buildTimedRevealPlan: wbBuildTimedRevealPlan,
  buildSpeechRenderPlan: wbBuildSpeechRenderPlan,
  executeSpeechPlan: wbExecuteSpeechPlan,
  revealBoundaryText: wbRevealBoundaryText,
  normalizeMathDisplayText: wbNormalizeMathDisplayText,
  extractMathExpression: wbExtractMathExpression,
  getMathCaption: wbGetMathCaption,
  toSpeechFriendlyText: wbToSpeechFriendlyText,
  normalizeComparableText: wbNormalizeComparableText,
};

if (typeof window !== 'undefined') {
  window.Whiteboard = Whiteboard;
  window.WhiteboardTestUtils = WhiteboardTestUtils;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Whiteboard, WhiteboardTestUtils };
}
