"""Create first-run local settings without overwriting existing credentials."""
import os
from pathlib import Path
import secrets


def initialize(root: Path) -> bool:
    template = (root / '.env.example').read_text()
    values = {
        'OLLAMA_MODEL': 'qwen3:4b',
        'POSTGRES_PASSWORD': secrets.token_hex(24),
    }
    lines = [f'{line.split("=", 1)[0]}={values[line.split("=", 1)[0]]}'
             if '=' in line and line.split('=', 1)[0] in values else line
             for line in template.splitlines()]
    try:
        fd = os.open(root / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as stream:
        stream.write('\n'.join(lines) + '\n')
    return True


if __name__ == '__main__':
    created = initialize(Path(__file__).resolve().parents[1])
    print('Created private .env for local Qwen3-4B.' if created else 'Existing .env preserved; check its OLLAMA_MODEL before pulling weights.')
    print('Next: ollama pull qwen3:4b; then docker compose up -d --build --wait --wait-timeout 300')
