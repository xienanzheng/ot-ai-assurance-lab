"""Download the pinned research base into this user's cache; does not train."""
from pathlib import Path
import platform


def main():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This MLX training recipe requires an Apple Silicon Mac.')
    from huggingface_hub import snapshot_download
    snapshot = snapshot_download(
        repo_id='mlx-community/Qwen3-4B-4bit',
        revision='4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25',
        cache_dir=str(Path.home() / '.cache/huggingface/hub'),
    )
    print('Pinned base available at:', snapshot)
    print('Next: follow TRAINING.md. No training or simulator changes were made.')


if __name__ == '__main__':
    main()
