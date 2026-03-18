from __future__ import annotations

from pathlib import Path

from src.tools.helpers import validate_path_within, validate_stack_name
from src.engine.knowledge import _validate_repo_url
from src.engine.execution import _check_interpreter_abuse


# -----------------------------------------------------------------------
# Fix 1: Command Injection — repo_url validation
# -----------------------------------------------------------------------


class TestRepoUrlValidation:
    """Ensure malicious repo_url values are rejected."""

    def test_valid_https_url(self):
        assert _validate_repo_url("https://github.com/user/repo.git") is None

    def test_valid_ssh_url(self):
        assert _validate_repo_url("git@github.com:user/repo.git") is None

    def test_reject_semicolon_injection(self):
        """repo_url = 'https://evil.com; rm -rf /' must be rejected."""
        err = _validate_repo_url("https://evil.com; rm -rf /")
        assert err is not None
        assert "shell meta-characters" in err or "Invalid" in err

    def test_reject_pipe_injection(self):
        err = _validate_repo_url("https://evil.com | cat /etc/passwd")
        assert err is not None

    def test_reject_ampersand_injection(self):
        err = _validate_repo_url("https://evil.com && rm -rf /")
        assert err is not None

    def test_reject_backtick_injection(self):
        err = _validate_repo_url("https://evil.com `whoami`")
        assert err is not None

    def test_reject_dollar_injection(self):
        err = _validate_repo_url("https://evil.com $(whoami)")
        assert err is not None

    def test_reject_empty(self):
        err = _validate_repo_url("")
        assert err is not None

    def test_reject_non_url(self):
        err = _validate_repo_url("/bin/rm -rf /")
        assert err is not None


# -----------------------------------------------------------------------
# Fix 2: Path Traversal — validate_path_within
# -----------------------------------------------------------------------


class TestPathTraversalPrevention:
    """Ensure ../../ attacks are blocked."""

    def test_valid_path(self, tmp_path: Path):
        root = tmp_path / "stacks"
        root.mkdir()
        child = root / "test.md"
        child.touch()
        result = validate_path_within(child, root)
        assert str(result).startswith(str(root.resolve()))

    def test_traversal_rejected(self, tmp_path: Path):
        root = tmp_path / "stacks"
        root.mkdir()
        evil_path = root / "../../etc/passwd"
        try:
            validate_path_within(evil_path, root)
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "traversal" in str(exc).lower()

    def test_double_dot_rejected(self, tmp_path: Path):
        root = tmp_path / "stacks"
        root.mkdir()
        evil_path = root / ".." / ".." / "config.py"
        try:
            validate_path_within(evil_path, root)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # expected


# -----------------------------------------------------------------------
# Fix 2b: Stack name validation
# -----------------------------------------------------------------------


class TestStackNameValidation:
    """Ensure stack names with traversal chars are rejected."""

    def test_valid_name(self):
        assert validate_stack_name("android_kotlin") is None

    def test_valid_name_with_dash(self):
        assert validate_stack_name("flutter-dart") is None

    def test_reject_traversal(self):
        err = validate_stack_name("../../etc")
        assert err is not None
        assert "Invalid" in err

    def test_reject_slash(self):
        err = validate_stack_name("path/to/evil")
        assert err is not None

    def test_reject_empty(self):
        err = validate_stack_name("")
        assert err is not None

    def test_reject_spaces(self):
        err = validate_stack_name("some name")
        assert err is not None


# -----------------------------------------------------------------------
# Issue 1 (Session 2): Living off the Land — interpreter inline guard
# -----------------------------------------------------------------------


class TestInterpreterInlineGuard:
    """Ensure interpreter inline flags are blocked."""

    def test_python_c_blocked(self):
        result = _check_interpreter_abuse(
            "python3", 'python3 -c "import os; os.system("rm -rf /")"'
        )
        assert result is not None
        assert "Living off the Land" in result

    def test_node_e_blocked(self):
        result = _check_interpreter_abuse("node", 'node -e "process.exit(1)"')
        assert result is not None

    def test_node_eval_blocked(self):
        result = _check_interpreter_abuse(
            "node", 'node --eval "require("child_process").exec("rm -rf /")"'
        )
        assert result is not None

    def test_ruby_e_blocked(self):
        result = _check_interpreter_abuse("ruby", 'ruby -e "system("rm -rf /")"')
        assert result is not None

    def test_perl_e_blocked(self):
        result = _check_interpreter_abuse("perl", 'perl -e "system("rm -rf /")"')
        assert result is not None

    def test_php_r_blocked(self):
        result = _check_interpreter_abuse("php", 'php -r "system("rm -rf /")"')
        assert result is not None

    def test_python_script_allowed(self):
        """python3 script.py should be fine."""
        result = _check_interpreter_abuse("python3", "python3 script.py")
        assert result is None

    def test_python_m_pytest_allowed(self):
        """python3 -m pytest tests/ should be allowed."""
        result = _check_interpreter_abuse("python3", "python3 -m pytest tests/")
        assert result is None

    def test_python_m_unsafe_blocked(self):
        """python3 -m http.client (not in safe list) should be blocked."""
        result = _check_interpreter_abuse("python3", "python3 -m http.client")
        assert result is not None

    def test_node_app_allowed(self):
        """node app.js should be fine."""
        result = _check_interpreter_abuse("node", "node app.js")
        assert result is None

    def test_non_interpreter_ignored(self):
        """git, ls, etc. should be ignored."""
        result = _check_interpreter_abuse("git", "git status")
        assert result is None
