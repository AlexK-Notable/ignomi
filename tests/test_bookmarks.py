"""
Tests for bookmark loading, saving, caching, XDG migration, and atomic writes.

Uses real JSON files on disk. Mocks only GTK/Ignis imports.
"""

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Patch GTK/Ignis modules for headless testing
_saved_modules = {}
_modules_to_fake = [
    "gi", "gi.repository", "gi.repository.Gdk", "gi.repository.GLib",
    "ignis", "ignis.services", "ignis.services.applications",
    "ignis.services.hyprland",
]
for _mod in _modules_to_fake:
    if _mod in sys.modules:
        _saved_modules[_mod] = sys.modules[_mod]

_fake_gi = types.ModuleType("gi")
_fake_gi_repo = types.ModuleType("gi.repository")
_fake_gi_repo.Gdk = MagicMock()
_fake_gi_repo.GLib = MagicMock()
_fake_gi.repository = _fake_gi_repo
_fake_ignis = types.ModuleType("ignis")
_fake_services = types.ModuleType("ignis.services")
_fake_apps = types.ModuleType("ignis.services.applications")
_fake_apps.ApplicationsService = MagicMock()
_fake_hyprland = types.ModuleType("ignis.services.hyprland")
_fake_hyprland.HyprlandService = MagicMock()
_fake_ignis.services = _fake_services
_fake_services.applications = _fake_apps
_fake_services.hyprland = _fake_hyprland

sys.modules["gi"] = _fake_gi
sys.modules["gi.repository"] = _fake_gi_repo
sys.modules["gi.repository.Gdk"] = _fake_gi_repo.Gdk
sys.modules["gi.repository.GLib"] = _fake_gi_repo.GLib
sys.modules["ignis"] = _fake_ignis
sys.modules["ignis.services"] = _fake_services
sys.modules["ignis.services.applications"] = _fake_apps
sys.modules["ignis.services.hyprland"] = _fake_hyprland

from utils.helpers import _deep_merge, load_bookmarks, save_bookmarks

# Restore modules
for _mod in _modules_to_fake:
    if _mod in _saved_modules:
        sys.modules[_mod] = _saved_modules[_mod]
    elif _mod in sys.modules:
        del sys.modules[_mod]


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
