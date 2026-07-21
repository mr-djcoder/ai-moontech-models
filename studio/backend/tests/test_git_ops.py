from app import git_ops


def test_commit_and_push_runs_expected_commands(tmp_path):
    calls = []
    def fake_run(cmd, cwd):
        calls.append((cmd, cwd))
        if cmd[:2] == ["git", "rev-parse"]:
            return "abc1234\n"
        return ""
    result = git_ops.commit_and_push(tmp_path, "models/jess", "feat: add jess", run=fake_run)
    assert result == "abc1234"
    commands = [c[0] for c in calls]
    assert ["git", "add", "models/jess"] in commands
    assert ["git", "commit", "-m", "feat: add jess"] in commands
    assert ["git", "push"] in commands
    assert any(c[0] == ["git", "rev-parse", "--short", "HEAD"] for c in calls)
    assert all(c[1] == tmp_path for c in calls)
