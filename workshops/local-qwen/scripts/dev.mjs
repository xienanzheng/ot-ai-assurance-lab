import { spawnSync } from 'node:child_process';
import { constants, copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const project = 'ot-qwen-workshop';

export function run(command, args, cwd = root, env = process.env) {
  const result = spawnSync(command, args, { cwd, env, stdio: 'inherit', shell: false });
  if (result.error) throw new Error(`Cannot run ${command}: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`${command} exited with ${result.status ?? result.signal}`);
}

export function npmInvocation(args, env = process.env) {
  if (!env.npm_execpath) throw new Error('Run this helper through npm install or npm run.');
  // Node + npm's JS entry works on Windows too, without shell parsing .cmd files.
  return [process.execPath, [env.npm_execpath, ...args]];
}

export function npm(args, cwd = root) { run(...npmInvocation(args), cwd); }

export function ensureIgnoreFile(cwd = root) {
  try { copyFileSync(join(cwd, 'gitignore.template'), join(cwd, '.gitignore'), constants.COPYFILE_EXCL); }
  catch (error) { if (error.code !== 'EEXIST') throw error; }
}

export function validatePackageFiles(paths) {
  const forbidden = paths.filter(path => /(^|\/)\.env(?:\.|$)|(^|\/)(?:\.venv[^/]*|node_modules|artifacts|release|__pycache__)(?:\/|$)|\.(?:pyc|safetensors|tgz)$/.test(path));
  if (forbidden.length) throw new Error(`Package contains ${forbidden.length} excluded file(s).`);
  for (const needed of ['package.json', 'web/package-lock.json', 'scripts/dev.mjs', 'pyproject.toml', 'gitignore.template']) {
    if (!paths.includes(needed)) throw new Error(`Package missing ${needed}`);
  }
}

export function checkPackage() {
  const [command, args] = npmInvocation(['pack', '--dry-run', '--ignore-scripts', '--json']);
  const result = spawnSync(command, args, { cwd: root, encoding: 'utf8', shell: false, maxBuffer: 5 * 1024 * 1024 });
  if (result.error || result.status !== 0) throw new Error('Unable to inspect npm package contents.');
  const paths = JSON.parse(result.stdout)[0].files.map(file => file.path);
  validatePackageFiles(paths);
  console.log(`Package checked: ${paths.length} source/evidence files; generated and private files excluded.`);
}

export function pythonVersionOK(output) {
  try {
    const [major, minor] = JSON.parse(output);
    return major === 3 && (minor === 12 || minor === 13);
  } catch { return false; }
}

export function findPython(exec = spawnSync, platform = process.platform, env = process.env) {
  const choices = env.OTLAB_PYTHON ? [[env.OTLAB_PYTHON, []]] : platform === 'win32'
    ? [['py', ['-3.13']], ['py', ['-3.12']], ['python', []]]
    : [['python3.13', []], ['python3.12', []], ['python3', []]];
  for (const [command, prefix] of choices) {
    const result = exec(command, [...prefix, '-c', 'import json,sys;print(json.dumps(list(sys.version_info[:2])))'],
      { encoding: 'utf8', timeout: 10000, shell: false });
    if (!result.error && result.status === 0 && pythonVersionOK(result.stdout)) return [command, prefix];
  }
  throw new Error('Install Python 3.12 or 3.13, or set OTLAB_PYTHON to its executable path.');
}

export function venvPython(folder, platform = process.platform) {
  return join(folder, platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'python.exe' : 'python');
}

export function ensureVenv(folder, cwd = root) {
  const python = venvPython(join(cwd, folder));
  if (!existsSync(join(cwd, folder))) {
    const [command, prefix] = findPython();
    run(command, [...prefix, '-m', 'venv', folder], cwd);
  }
  if (!existsSync(python)) throw new Error(`${folder} exists but is not a usable virtual environment. It was not overwritten.`);
  const result = spawnSync(python, ['-c', 'import json,sys;print(json.dumps(list(sys.version_info[:2])))'], { encoding: 'utf8' });
  if (result.error || result.status !== 0 || !pythonVersionOK(result.stdout)) throw new Error(`${folder} must use Python 3.12 or 3.13.`);
  return python;
}

export function requiredPython(training = false) {
  const python = venvPython(join(root, training ? '.venv-train' : '.venv'));
  if (!existsSync(python)) throw new Error(`Run npm run ${training ? 'train:setup' : 'setup'} first.`);
  return python;
}

export function trainingPlatform(platform = process.platform, arch = process.arch) {
  if (platform !== 'darwin' || arch !== 'arm64') throw new Error('This MLX recipe requires Apple Silicon. CPU checks and the Docker bench work separately.');
}

export function trainArguments(args, home = homedir()) {
  if (!args.includes('--stage') || !args.includes('--root')) throw new Error('Use npm run train -- --stage prepare --root artifacts/new-run (then follow TRAINING.md).');
  const model = join(home, '.cache/huggingface/hub/models--mlx-community--Qwen3-4B-4bit/snapshots/4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25');
  return ['-m', 'scripts.run_typed_training', ...args, ...(!args.includes('--model') ? ['--model', model] : [])];
}

export function doctor() {
  console.log(`Node ${process.version}; workshop ${root}`);
  try { console.log('Python:', findPython().join(' ')); } catch (error) { console.log(error.message); }
  for (const [command, args, label] of [
    ['docker', ['compose', 'version'], 'Docker Compose'],
    ['docker', ['info', '--format', '{{.ServerVersion}}'], 'Docker engine'],
    ['ollama', ['--version'], 'Ollama (optional)'],
  ]) {
    const result = spawnSync(command, args, { encoding: 'utf8', timeout: 10000, shell: false });
    console.log(`${label}: ${!result.error && result.status === 0 ? result.stdout.trim() : 'unavailable'}`);
  }
}

export function main(action, args = []) {
  switch (action) {
    case 'install': ensureIgnoreFile(); npm(['ci'], join(root, 'web')); break;
    case 'setup': run(ensureVenv('.venv'), ['-m', 'pip', 'install', '-e', '.[test]']); break;
    case 'doctor': doctor(); break;
    case 'test': run(requiredPython(), ['-m', 'pytest', '-q', ...args]); break;
    case 'review': run(requiredPython(), ['scripts/review_saved_results.py']); break;
    case 'up': {
      if (!existsSync(join(root, '.env'))) {
        const [command, prefix] = findPython();
        run(command, [...prefix, 'scripts/preflight.py', '--init']);
      }
      run('docker', ['compose', '-p', project, 'up', '-d', '--build', '--wait', '--wait-timeout', '300']);
      console.log('Bench: http://127.0.0.1:18790. Edit UI: npm run dev → http://127.0.0.1:18791.');
      break;
    }
    case 'down': run('docker', ['compose', '-p', project, 'down']); break;
    case 'train-setup':
      trainingPlatform(); run(ensureVenv('.venv-train'), ['-m', 'pip', 'install', '-r', 'requirements-training.txt']); break;
    case 'train-model':
      trainingPlatform(); run(requiredPython(true), ['scripts/download_training_model.py']); break;
    case 'train':
      trainingPlatform(); run(requiredPython(true), trainArguments(args), root,
        { ...process.env, HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1', PYTHONUNBUFFERED: '1' }); break;
    case 'package': {
      const destination = join(root, 'release'); mkdirSync(destination, { recursive: true });
      npm(['pack', '--pack-destination', destination]); break;
    }
    case 'check-package': checkPackage(); break;
    default: throw new Error(`Unknown command: ${action ?? '(missing)'}`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(process.argv[2], process.argv.slice(3)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
