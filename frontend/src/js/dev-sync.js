function makeFixturePackage(id, section, steps, options = {}) {
  const markers = (options.markers || steps.map((step, index) => ({
    name: step.step_id,
    time_ms: index * 1100,
  }))).map(marker => ({ ...marker }));

  return {
    package_id: id,
    section,
    steps: steps.map(step => ({ ...step })),
    audio_url: options.audio_url || null,
    audio_provider: options.audio_provider || 'mock',
    audio_duration_ms: options.audio_duration_ms || (markers.at(-1)?.time_ms || 0) + 1200,
    markers,
    transcript: steps.map(step => step.spoken_text).filter(Boolean).join('\n\n'),
    resume_cursor: {
      package_id: id,
      section,
      step_id: steps[0]?.step_id || null,
      audio_offset_ms: options.audio_offset_ms || 0,
    },
  };
}

function buildResumePackage(original, cursor) {
  if (!original || !cursor?.stepId) {
    return null;
  }

  const stepIndex = original.steps.findIndex(step => step.step_id === cursor.stepId);
  if (stepIndex < 0) {
    return null;
  }

  const startMarkerMs = original.markers.find(marker => marker.name === cursor.stepId)?.time_ms || 0;
  const steps = original.steps.slice(stepIndex).map(step => ({ ...step }));
  const markers = original.markers
    .filter(marker => steps.some(step => step.step_id === marker.name))
    .map(marker => ({ name: marker.name, time_ms: Math.max(0, marker.time_ms - startMarkerMs) }));

  return makeFixturePackage(
    `${original.package_id}-resume`,
    original.section,
    steps,
    {
      audio_provider: original.audio_provider,
      audio_url: original.audio_url,
      audio_duration_ms: Math.max(1200, original.audio_duration_ms - startMarkerMs),
      markers,
      audio_offset_ms: cursor.audioOffsetMs || 0,
    }
  );
}

const SyncFixtures = {
  'browser-speech-text': makeFixturePackage(
    'fixture-browser-text',
    'intuition',
    [
      {
        step_id: 'intro_step_1',
        kind: 'heading',
        display_text: 'Understanding convergence',
        spoken_text: 'Understanding convergence.',
        reveal_mode: 'instant',
      },
      {
        step_id: 'intro_step_2',
        kind: 'text',
        display_text: 'A sequence converges when its terms settle toward one target value.',
        spoken_text: 'A sequence converges when its terms settle toward one target value.',
        reveal_mode: 'token',
      },
      {
        step_id: 'intro_step_3',
        kind: 'text',
        display_text: 'We first build the intuition.\nThen we translate it into the formal epsilon language.',
        spoken_text: 'We first build the intuition. Then we translate it into the formal epsilon language.',
        reveal_mode: 'line',
      },
    ]
  ),
  'browser-speech-math': makeFixturePackage(
    'fixture-browser-math',
    'formal_definition',
    [
      {
        step_id: 'math_step_1',
        kind: 'heading',
        display_text: 'Formal statement',
        spoken_text: 'Formal statement.',
        reveal_mode: 'instant',
      },
      {
        step_id: 'math_step_2',
        kind: 'math',
        display_text: '$$\\forall \\varepsilon > 0\\; \\exists N\\; \\text{such that}\\; n \\ge N \\Rightarrow |x_n - L| < \\varepsilon$$',
        spoken_text: 'For every positive epsilon, there exists an N so that once n is at least N, the distance between x sub n and L is smaller than epsilon.',
        reveal_mode: 'line',
      },
      {
        step_id: 'math_step_3',
        kind: 'text',
        display_text: 'The quantifiers say we can make the terms as close as we like by going far enough out in the sequence.',
        spoken_text: 'The quantifiers say we can make the terms as close as we like by going far enough out in the sequence.',
        reveal_mode: 'token',
      },
    ]
  ),
  'math-rendering-regression': makeFixturePackage(
    'fixture-math-rendering',
    'homology',
    [
      {
        step_id: 'render_step_1',
        kind: 'heading',
        display_text: 'Homology notation',
        spoken_text: 'Homology notation.',
        reveal_mode: 'token',
      },
      {
        step_id: 'render_step_2',
        kind: 'text',
        display_text: "We'll be using concepts from algebraic topology, so make sure you're familiar with those.",
        spoken_text: "We'll be using concepts from algebraic topology, so make sure you're familiar with those.",
        reveal_mode: 'token',
      },
      {
        step_id: 'render_step_3',
        kind: 'math',
        display_text: 'H_n(X) = \f' + 'rac{Z_n(X)}{B_n(X)}',
        spoken_text: 'Here H sub n of X is the quotient of cycles modulo boundaries.',
        reveal_mode: 'line',
      },
      {
        step_id: 'render_step_4',
        kind: 'highlight',
        display_text: "Having a good grasp of these prerequisites is essential for everything we'll cover in homology.",
        spoken_text: "Having a good grasp of these prerequisites is essential for everything we'll cover in homology.",
        reveal_mode: 'token',
        target: 'render_step_2',
      },
    ]
  ),
  'interrupt-resume': makeFixturePackage(
    'fixture-interrupt',
    'example',
    [
      {
        step_id: 'resume_step_1',
        kind: 'heading',
        display_text: 'Worked example',
        spoken_text: 'Worked example.',
        reveal_mode: 'instant',
      },
      {
        step_id: 'resume_step_2',
        kind: 'text',
        display_text: 'Take x sub n equals one over n. The terms shrink toward zero.',
        spoken_text: 'Take x sub n equals one over n. The terms shrink toward zero.',
        reveal_mode: 'token',
      },
      {
        step_id: 'resume_step_3',
        kind: 'text',
        display_text: 'To make one over n smaller than epsilon, we choose n large enough so that n is bigger than one over epsilon.',
        spoken_text: 'To make one over n smaller than epsilon, we choose n large enough so that n is bigger than one over epsilon.',
        reveal_mode: 'token',
      },
    ]
  ),
  'audio-error-fallback': makeFixturePackage(
    'fixture-audio-fallback',
    'fallback_demo',
    [
      {
        step_id: 'fallback_step_1',
        kind: 'heading',
        display_text: 'Forced audio fallback',
        spoken_text: 'Forced audio fallback.',
        reveal_mode: 'instant',
      },
      {
        step_id: 'fallback_step_2',
        kind: 'text',
        display_text: 'This fixture starts on the real audio path and then falls back to browser speech when the clip fails to load.',
        spoken_text: 'This fixture starts on the real audio path and then falls back to browser speech when the clip fails to load.',
        reveal_mode: 'token',
      },
    ],
    {
      audio_provider: 'polly',
      audio_url: '/missing-sync-fixture.mp3',
    }
  ),
};

let lastInterruptedPackage = null;
let lastResumeCursor = null;

function setDebugEnabled(enabled) {
  window.KS_SYNC_DEBUG = enabled;
  try {
    window.localStorage.setItem('ks.syncDebug', enabled ? '1' : '0');
  } catch (_error) {
    // Ignore storage issues in the harness.
  }
  if (window.__KS_SYNC_DEBUG__) {
    window.__KS_SYNC_DEBUG__.enabled = enabled;
    if (!enabled) {
      window.__KS_SYNC_DEBUG__.clear();
    }
  }
  renderSyncLog();
}

function renderResumeLog() {
  const el = document.getElementById('resume-log');
  if (!el) return;
  el.textContent = lastResumeCursor
    ? JSON.stringify(lastResumeCursor, null, 2)
    : 'No interruption captured yet.';
}

function renderSyncLog() {
  const el = document.getElementById('sync-log');
  if (!el) return;

  const store = window.__KS_SYNC_DEBUG__;
  if (!store?.enabled) {
    el.textContent = 'Sync debug is off.';
    return;
  }

  el.textContent = store.events.length
    ? JSON.stringify(store.events, null, 2)
    : 'Waiting for sync events...';
}

async function runSelectedFixture() {
  const select = document.getElementById('fixture-select');
  const fixtureKey = select?.value || 'browser-speech-text';
  const fixture = SyncFixtures[fixtureKey];
  if (!fixture) {
    return;
  }

  Whiteboard.clear();
  if (window.__KS_SYNC_DEBUG__) {
    window.__KS_SYNC_DEBUG__.clear();
  }
  lastInterruptedPackage = fixture;
  lastResumeCursor = null;
  renderResumeLog();
  renderSyncLog();
  await Whiteboard.playPackage({ ...fixture, steps: fixture.steps.map(step => ({ ...step })) });
  renderSyncLog();
}

function interruptFixture() {
  if (!Whiteboard.isPlaying()) {
    return;
  }
  lastResumeCursor = Whiteboard.interruptPlayback();
  renderResumeLog();
  renderSyncLog();
}

async function resumeFixture() {
  if (!lastInterruptedPackage || !lastResumeCursor) {
    return;
  }
  const resumePackage = buildResumePackage(lastInterruptedPackage, lastResumeCursor);
  if (!resumePackage) {
    return;
  }
  await Whiteboard.playPackage(resumePackage);
  renderSyncLog();
}

document.getElementById('run-fixture')?.addEventListener('click', () => {
  void runSelectedFixture();
});

document.getElementById('interrupt-fixture')?.addEventListener('click', () => {
  interruptFixture();
});

document.getElementById('resume-fixture')?.addEventListener('click', () => {
  void resumeFixture();
});

document.getElementById('clear-fixture')?.addEventListener('click', () => {
  Whiteboard.clear();
  lastInterruptedPackage = null;
  lastResumeCursor = null;
  if (window.__KS_SYNC_DEBUG__) {
    window.__KS_SYNC_DEBUG__.clear();
  }
  renderResumeLog();
  renderSyncLog();
});

document.getElementById('debug-toggle')?.addEventListener('change', event => {
  setDebugEnabled(Boolean(event.target?.checked));
});

const initialDebugEnabled = (() => {
  try {
    return window.localStorage.getItem('ks.syncDebug') === '1';
  } catch (_error) {
    return false;
  }
})();

const debugToggle = document.getElementById('debug-toggle');
if (debugToggle) {
  debugToggle.checked = initialDebugEnabled;
}
setDebugEnabled(initialDebugEnabled);
renderResumeLog();
renderSyncLog();
setInterval(renderSyncLog, 300);
