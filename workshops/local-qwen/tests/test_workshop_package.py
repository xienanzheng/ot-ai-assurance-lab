from pathlib import Path
import shutil
import pytest
from scripts.review_saved_results import review
from training.mlx_experiment import PINNED_MODEL, PIN

ROOT = Path(__file__).resolve().parents[1]


def test_saved_results_and_readiness():
    result = review(ROOT / 'evidence/typed-qwen-2026-10-31')
    assert result['base']['decision_correct'] == 32
    assert result['selected']['decision_correct'] == 41
    assert result['selected']['supported_correct'] == 34
    assert result['selected']['classes']['hold'] == {'count': 32, 'correct': 0}
    assert result['readiness']['ready'] is False


def test_rejects_modified_evidence(tmp_path):
    folder = tmp_path / 'evidence'
    shutil.copytree(ROOT / 'evidence/typed-qwen-2026-10-31', folder)
    with (folder / 'selected-test.rows.jsonl').open('a') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        review(folder)


def test_model_path_uses_current_home():
    assert PINNED_MODEL == Path.home() / '.cache/huggingface/hub/models--mlx-community--Qwen3-4B-4bit/snapshots' / PIN
