const assert = require('node:assert/strict');
const test = require('node:test');

const { WhiteboardTestUtils } = require('../src/js/whiteboard.js');

function runSpeechPlan(plan, speakerScript) {
  const renders = [];
  const events = [];

  return new Promise((resolve, reject) => {
    WhiteboardTestUtils.executeSpeechPlan(plan, {
      createUtterance(text) {
        return { text };
      },
      speak(utterance) {
        speakerScript(utterance);
      },
      onRender(text) {
        renders.push(text);
      },
      onEvent(type, detail = {}) {
        events.push({ type, detail });
      },
      onDone() {
        resolve({ renders, events });
      },
      onError(error) {
        reject(error);
      },
    });
  });
}

test('token reveal plan counts whitespace and newline units in its timing budget', () => {
  const text = 'The key idea\nis to move one step at a time.';
  const tokenCount = WhiteboardTestUtils.tokenize(text).length;
  const plan = WhiteboardTestUtils.buildTimedRevealPlan(text, 'token', 1200);

  assert.equal(plan.units.length, tokenCount);
  assert.equal(plan.intervalMs, Math.max(10, Math.floor(1200 / tokenCount)));
});

test('timed reveal plan honors instant and line modes', () => {
  const instant = WhiteboardTestUtils.buildTimedRevealPlan('Quick heading', 'instant', 900);
  assert.deepEqual(instant.units, ['Quick heading']);
  assert.equal(instant.intervalMs, 0);

  const line = WhiteboardTestUtils.buildTimedRevealPlan(
    'First sentence. Second sentence.',
    'line',
    900
  );
  assert.deepEqual(line.units, ['First sentence. ', 'Second sentence.']);
  assert.equal(line.intervalMs, Math.max(10, Math.floor(900 / 2)));
});

test('speech render plan chooses boundary sync for matching token text when supported', () => {
  const plan = WhiteboardTestUtils.buildSpeechRenderPlan(
    {
      kind: 'text',
      display_text: 'Hello world',
      spoken_text: 'Hello world',
      reveal_mode: 'token',
    },
    { boundarySupported: true }
  );

  assert.equal(plan.strategy, 'boundary');
});

test('speech render plan falls back to chunked line sync when boundary sync is unavailable', () => {
  const plan = WhiteboardTestUtils.buildSpeechRenderPlan(
    {
      kind: 'text',
      display_text: 'First sentence. Second sentence.',
      spoken_text: 'First sentence. Second sentence.',
      reveal_mode: 'line',
    },
    { boundarySupported: false }
  );

  assert.equal(plan.strategy, 'chunked');
  assert.deepEqual(plan.displayChunks, ['First sentence. ', 'Second sentence.']);
  assert.deepEqual(plan.speechChunks, ['First sentence. ', 'Second sentence.']);
});

test('speech render plan allows highlight notes to reveal progressively', () => {
  const plan = WhiteboardTestUtils.buildSpeechRenderPlan(
    {
      kind: 'highlight',
      display_text: 'Focus on this definition.',
      spoken_text: 'Focus on this definition.',
      reveal_mode: 'token',
    },
    { boundarySupported: true }
  );

  assert.equal(plan.strategy, 'boundary');
});

test('math normalization repairs JSON-escaped control characters and extracts display math', () => {
  const malformed = '\f' + 'rac{Z_n(X)}{B_n(X)}';
  const normalized = WhiteboardTestUtils.normalizeMathDisplayText(malformed);
  const extracted = WhiteboardTestUtils.extractMathExpression(malformed);

  assert.equal(normalized, '$$\\frac{Z_n(X)}{B_n(X)}$$');
  assert.equal(extracted.expression, '\\frac{Z_n(X)}{B_n(X)}');
  assert.equal(extracted.displayMode, true);
});

test('math caption is kept when spoken explanation adds content beyond the formula', () => {
  const caption = WhiteboardTestUtils.getMathCaption({
    display_text: '$$\\frac{Z_n(X)}{B_n(X)}$$',
    spoken_text: 'Here H sub n of X is the quotient of cycles modulo boundaries.',
  });

  assert.equal(
    caption,
    'Here H sub n of X is the quotient of cycles modulo boundaries.'
  );
});

test('boundary speech execution never renders ahead of the latest boundary event', async () => {
  const plan = WhiteboardTestUtils.buildSpeechRenderPlan(
    {
      kind: 'text',
      display_text: 'Hello world',
      spoken_text: 'Hello world',
      reveal_mode: 'token',
    },
    { boundarySupported: true }
  );

  const result = await runSpeechPlan(plan, utterance => {
    utterance.onstart?.();
    utterance.onboundary?.({ charIndex: 6 });
    utterance.onboundary?.({ charIndex: 11 });
    utterance.onend?.();
  });

  assert.deepEqual(result.renders, ['', 'Hello ', 'Hello world', 'Hello world']);
  assert.deepEqual(
    result.events.map(event => event.type),
    ['utterance_start', 'first_boundary', 'render_complete', 'utterance_end']
  );
});

test('chunked speech execution reveals text chunk by chunk and finishes on the last utterance', async () => {
  const plan = WhiteboardTestUtils.buildSpeechRenderPlan(
    {
      kind: 'text',
      display_text: 'First sentence. Second sentence.',
      spoken_text: 'First sentence. Second sentence.',
      reveal_mode: 'line',
    },
    { boundarySupported: false }
  );

  let callCount = 0;
  const result = await runSpeechPlan(plan, utterance => {
    callCount += 1;
    utterance.onstart?.();
    utterance.onend?.();
  });

  assert.equal(callCount, 2);
  assert.deepEqual(result.renders, ['First sentence. ', 'First sentence. Second sentence.']);
  assert.deepEqual(
    result.events.map(event => event.type),
    ['utterance_start', 'render_complete', 'utterance_end']
  );
});
