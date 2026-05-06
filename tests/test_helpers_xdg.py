"""
Tests for the bookmarks XDG migration path.

`_bookmarks_path()` migrates the in-repo seed bookmarks to ~/.local/share/
on first use. After migration, the in-repo file is unused.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.helpers import _bookmarks_path


@pytest.fixture
def fake_xdg_home(tmp_path, monkeypatch):
    """Redirect HOME so XDG path lands in a tmp directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() reads from HOME on Linux
    return tmp_path


def test_returns_xdg_path_when_xdg_already_exists(fake_xdg_home):
    """If XDG bookmarks exists, return it without touching in-repo source."""
    xdg = fake_xdg_home / ".local" / "share" / "ignomi" / "bookmarks.json"
    xdg.parent.mkdir(parents=True)
    xdg.write_text('{"bookmarks": ["firefox.desktop"]}')

    result = _bookmarks_path()
    assert result == xdg
    assert result.exists()


def test_migrates_in_repo_to_xdg_when_xdg_missing(fake_xdg_home, tmp_path):
    """First call with no XDG file but in-repo source → copy to XDG."""
    # Create a fake "in-repo" source file
    repo_dir = tmp_path / "fake-repo" / "data"
    repo_dir.mkdir(parents=True)
    repo_bookmarks = repo_dir / "bookmarks.json"
    repo_bookmarks.write_text('{"bookmarks": ["seed.desktop"]}')

    # Patch the resolution of "in-repo source" path inside _bookmarks_path
    fake_helpers_file = tmp_path / "fake-repo" / "utils" / "helpers.py"
    fake_helpers_file.parent.mkdir(parents=True, exist_ok=True)
    fake_helpers_file.touch()

    with patch("utils.helpers.__file__", str(fake_helpers_file)):
        result = _bookmarks_path()

    xdg = fake_xdg_home / ".local" / "share" / "ignomi" / "bookmarks.json"
    assert result == xdg
    assert xdg.exists()
    # Migration is content-faithful
    data = json.loads(xdg.read_text())
    assert data == {"bookmarks": ["seed.desktop"]}


def test_returns_xdg_path_even_when_neither_exists(fake_xdg_home, tmp_path):
    """Returns XDG path (caller decides what to do with non-existent file)."""
    # Point the helpers module's __file__ at a fake path with no data dir,
    # so _bookmarks_path can't migrate from in-repo seed.
    nowhere = tmp_path / "nowhere" / "utils" / "helpers.py"
    nowhere.parent.mkdir(parents=True, exist_ok=True)
    nowhere.touch()
    with patch("utils.helpers.__file__", str(nowhere)):
        result = _bookmarks_path()
    expected = fake_xdg_home / ".local" / "share" / "ignomi" / "bookmarks.json"
    assert result == expected
    # Path is returned even though file doesn't exist — caller checks .exists()
    assert not result.exists()


def test_migration_is_idempotent(fake_xdg_home, tmp_path):
    """Calling twice should not re-migrate (XDG file is now source of truth)."""
    repo_dir = tmp_path / "fake-repo" / "data"
    repo_dir.mkdir(parents=True)
    repo_bookmarks = repo_dir / "bookmarks.json"
    repo_bookmarks.write_text('{"bookmarks": ["original.desktop"]}')

    fake_helpers_file = tmp_path / "fake-repo" / "utils" / "helpers.py"
    fake_helpers_file.parent.mkdir(parents=True, exist_ok=True)
    fake_helpers_file.touch()

    with patch("utils.helpers.__file__", str(fake_helpers_file)):
        # First call migrates
        first = _bookmarks_path()

        # Modify the XDG file — second call should preserve user's edits,
        # NOT re-copy from the (now-stale) in-repo source.
        first.write_text('{"bookmarks": ["user-edited.desktop"]}')

        # Modify the in-repo source too — must not re-migrate
        repo_bookmarks.write_text('{"bookmarks": ["should-not-appear.desktop"]}')

        second = _bookmarks_path()

    assert first == second
    data = json.loads(second.read_text())
    assert data == {"bookmarks": ["user-edited.desktop"]}
