import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { run, npm, findPython } from '../workshops/local-qwen/scripts/dev.mjs';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const workshop = join(root, 'workshops/local-qwen');

function initialize() {
  if (!existsSync(join(root, '.env'))) {
    const [command, prefix] = findPython();
    run(command, [...prefix, 'scripts/setup_local.py'], root);
  }
}

export function main(action) {
  switch (action) {
    case 'install':
      npm(['ci'], join(root, 'services/web'));
      npm(['ci'], workshop);
      console.log('UI dependencies installed. Next: npm run setup. No models downloaded or services started.');
      break;
    case 'setup': npm(['run', 'setup'], workshop); initialize(); break;
    case 'doctor': npm(['run', 'doctor'], workshop); break;
    case 'up': initialize(); run('docker', ['compose', 'up', '-d', '--build', '--wait', '--wait-timeout', '300'], root); break;
    case 'down': run('docker', ['compose', 'down'], root); break;
    case 'package': {
      const destination = join(root, 'release'); mkdirSync(destination, { recursive: true });
      npm(['pack', '--pack-destination', destination], workshop); break;
    }
    default: throw new Error(`Unknown command: ${action ?? '(missing)'}`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(process.argv[2]); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
