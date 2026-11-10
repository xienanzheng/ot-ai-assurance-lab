import test from 'node:test';
import assert from 'node:assert/strict';
import { main, root, workshop } from '../scripts/develop.mjs';
import { join } from 'node:path';

test('root helper uses its own checkout and separate workshop', () => {
  assert.equal(workshop, join(root, 'workshops/local-qwen'));
  assert.throws(() => main('not-a-command'), /Unknown command/);
});
