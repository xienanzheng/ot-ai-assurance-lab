import os
from scripts.setup_local import initialize


def test_creates_private_unique_local_configuration(tmp_path):
    (tmp_path / '.env.example').write_text('OLLAMA_MODEL=qwen3:8b\nPOSTGRES_PASSWORD=old\nOPENROUTER_API_KEY=\n')
    assert initialize(tmp_path)
    config = (tmp_path / '.env').read_text()
    assert 'OLLAMA_MODEL=qwen3:4b' in config
    assert 'POSTGRES_PASSWORD=old' not in config
    assert 'OPENROUTER_API_KEY=\n' in config
    if os.name != 'nt':
        assert (tmp_path / '.env').stat().st_mode & 0o777 == 0o600
    other = tmp_path / 'other'; other.mkdir()
    (other / '.env.example').write_text((tmp_path / '.env.example').read_text())
    initialize(other)
    assert (other / '.env').read_text() != config


def test_preserves_existing_environment(tmp_path):
    (tmp_path / '.env.example').write_text('OLLAMA_MODEL=qwen3:8b\n')
    path = tmp_path / '.env'; path.write_text('user-owned configuration\n')
    assert not initialize(tmp_path)
    assert path.read_text() == 'user-owned configuration\n'
