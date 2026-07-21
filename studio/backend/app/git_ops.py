import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def commit_and_push(repo_root: Path, add_path: str, message: str, run=_run) -> str:
    run(["git", "add", add_path], repo_root)
    run(["git", "commit", "-m", message], repo_root)
    run(["git", "push"], repo_root)
    sha = run(["git", "rev-parse", "--short", "HEAD"], repo_root)
    return sha.strip()
