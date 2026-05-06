"""
Tests for bookmark loading, saving, caching, XDG migration, and atomic
writes. Uses real JSON files on disk. Ignis/GTK module mocks are
installed by conftest.py.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.helpers import _deep_merge, load_bookmarks, save_bookmarks


@pytest.fixture(autouse=True)
def reset_bookmarks_cache():
    """Reset bookmarks cache before each test."""
    import utils.helpers as h
    h._bookmarks_cache = None
    yield
    h._bookmarks_cache = None


class TestLoadBookmarks:
    """Test loading bookmarks from JSON files."""

    def test_load_returns_list(self, tmp_bookmarks):
        with patch("utils.helpers._bookmarks_path", return_value=tmp_bookmarks):
            result = load_bookmarks()
        assert isinstance(result, list)

    def test_load_returns_expected_entries(self, tmp_bookmarks):
        with patch("utils.helpers._bookmarks_path", return_value=tmp_bookmarks):
            result = load_bookmarks()
        assert "firefox.desktop" in result
        assert "code.desktop" in result
        assert "nautilus.desktop" in result
        assert len(result) == 3

    def test_load_returns_empty_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("utils.helpers._bookmarks_path", return_value=missing):
            result = load_bookmarks()
        assert result == []

    def test_load_returns_empty_for_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json!!!")
        with patch("utils.helpers._bookmarks_path", return_value=bad_file):
            result = load_bookmarks()
        assert result == []

    def test_load_returns_copy_not_reference(self, tmp_bookmarks):
        with patch("utils.helpers._bookmarks_path", return_value=tmp_bookmarks):
            result1 = load_bookmarks()
            result2 = load_bookmarks()
        # Should be equal but not the same object
        assert result1 == result2
        result1.append("mutated.desktop")
        assert "mutated.desktop" not in load_bookmarks()


class TestSaveBookmarks:
    """Test saving bookmarks to JSON files."""

    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "bookmarks.json"
        with patch("utils.helpers._bookmarks_path", return_value=path):
            save_bookmarks(["a.desktop", "b.desktop"])
        assert path.exists()

    def test_save_roundtrip(self, tmp_path):
        path = tmp_path / "bookmarks.json"
        original = ["firefox.desktop", "code.desktop"]
        with patch("utils.helpers._bookmarks_path", return_value=path):
            save_bookmarks(original)
        data = json.loads(path.read_text())
        assert data["bookmarks"] == original

    def test_atomic_write_no_partial(self, tmp_path):
        """Verify .tmp file is cleaned up after save."""
        path = tmp_path / "bookmarks.json"
        with patch("utils.helpers._bookmarks_path", return_value=path):
            save_bookmarks(["test.desktop"])
        tmp_file = path.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_save_updates_cache(self, tmp_path):
        """After save, subsequent load should return saved data without re-reading disk."""
        path = tmp_path / "bookmarks.json"
        with patch("utils.helpers._bookmarks_path", return_value=path):
            save_bookmarks(["cached.desktop"])
            result = load_bookmarks()
        assert result == ["cached.desktop"]


class TestBookmarksCaching:
    """Test that bookmark cache works correctly."""

    def test_cache_hit_avoids_disk_read(self, tmp_bookmarks):
        with patch("utils.helpers._bookmarks_path", return_value=tmp_bookmarks):
            load_bookmarks()  # First load populates cache
            # Delete the file — cache should still work
            tmp_bookmarks.unlink()
            result = load_bookmarks()
        assert len(result) == 3
