import test from 'node:test';
import assert from 'node:assert/strict';
import { npmInvocation, findPython, pythonVersionOK, venvPython, trainingPlatform, trainArguments, main, ensureIgnoreFile, validatePackageFiles } from '../scripts/dev.mjs';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('npm paths and arguments stay separate without a shell', () => {
  const args = ['ci', '--prefix', 'folder with spaces;literal'];
  const [command, invocation] = npmInvocation(args, { npm_execpath: '/program files/npm/bin/npm-cli.js' });
  assert.equal(command, process.execPath);
  assert.deepEqual(invocation, ['/program files/npm/bin/npm-cli.js', ...args]);
  assert.throws(() => npmInvocation([], {}), /npm install/);
});
test('Python version gate rejects unsupported or malformed versions', () => {
  assert.ok(pythonVersionOK('[3,13]')); assert.ok(pythonVersionOK('[3,12]'));
  for (const value of ['[3,11]', '[3,14]', '[2,13]', 'not json']) assert.equal(pythonVersionOK(value), false);
});
test('Python discovery supports Windows launcher arguments and ignores missing executables', () => {
  const calls = [];
  const selected = findPython((cmd, args, options) => {
    calls.push([cmd,args]); assert.equal(options.shell, false);
    return args[0] === '-3.12' ? {status:0, stdout:'[3,12]'} : {status:1};
  }, 'win32', {});
  assert.deepEqual(selected, ['py', ['-3.12']]); assert.equal(calls.length, 2);
});
test('explicit Python path is one executable, not a shell command', () => {
  const path = '/A Folder/python3';
  assert.deepEqual(findPython((command) => {
    assert.equal(command, path); return {status:0,stdout:'[3,13]'};
  }, 'darwin', {OTLAB_PYTHON:path}), [path, []]);
  assert.throws(() => findPython(() => ({error: new Error('missing')}), 'linux', {}), /Install Python/);
});
test('venv locations and training platform checks are explicit', () => {
  assert.match(venvPython('env', 'win32'), /Scripts[/\\]python.exe$/);
  assert.match(venvPython('env', 'linux'), /bin[/\\]python$/);
  trainingPlatform('darwin', 'arm64');
  assert.throws(() => trainingPlatform('linux', 'x64'), /Apple Silicon/);
});
test('training requires explicit stage and experiment, preserving argument boundaries', () => {
  assert.throws(() => trainArguments([]), /--root/);
  const args = trainArguments(['--stage','prepare','--root','artifacts/a b'], '/People/A B');
  assert.equal(args[5], 'artifacts/a b');
  assert.equal(args.at(-2), '--model'); assert.match(args.at(-1), /^\/People\/A B\//);
  const custom = trainArguments(['--stage','prepare','--root','x','--model','fixed path']);
  assert.equal(custom.filter(x => x === '--model').length, 1);
});
test('unknown action fails before starting any process', () => {
  assert.throws(() => main('not-a-command'), /Unknown command/);
});
test('tarball install creates ignore rules without replacing user edits', () => {
  const folder = mkdtempSync(join(tmpdir(), 'ot-ignore-test-'));
  try {
    writeFileSync(join(folder, 'gitignore.template'), '.env\nartifacts/\n');
    ensureIgnoreFile(folder);
    assert.equal(readFileSync(join(folder, '.gitignore'), 'utf8'), '.env\nartifacts/\n');
    writeFileSync(join(folder, '.gitignore'), 'my changes\n'); ensureIgnoreFile(folder);
    assert.equal(readFileSync(join(folder, '.gitignore'), 'utf8'), 'my changes\n');
  } finally { rmSync(folder, { recursive: true }); }
});
test('package check requires reproducible inputs and excludes private/generated files', () => {
  const base = ['package.json', 'web/package-lock.json', 'scripts/dev.mjs', 'pyproject.toml', 'gitignore.template'];
  validatePackageFiles(base);
  for (const bad of ['.env', '.env.local', 'scripts/__pycache__/x.pyc', '.venv/lib/x', 'artifacts/run.json', 'x.safetensors', 'node_modules/x']) {
    assert.throws(() => validatePackageFiles([...base, bad]), /excluded/);
  }
  assert.throws(() => validatePackageFiles(['package.json']), /missing/);
});
