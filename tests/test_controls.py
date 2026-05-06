"""
Tests for SystemControlsHandler.

The handler runs on every keystroke (priority 50, highest of all handlers),
and gracefully degrades when AudioService/BacklightService are unavailable.
Both branches of each availability guard need verification.

Module-level mocks (gi, ignis.widgets, ignis.services.audio/backlight) come
from conftest.py; tests patch the per-handler availability getters as needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from search.handlers.controls import (
    BRIGHTNESS_KEYWORDS,
    MUTE_KEYWORDS,
    VOLUME_KEYWORDS,
    SystemControlsHandler,
)


class TestMatchesGate:
    """Audio/backlight availability gates the matches() result."""

    def test_no_match_when_audio_unavailable(self):
        h = SystemControlsHandler()
        with patch.object(h, "_audio_available", return_value=False):
            for kw in VOLUME_KEYWORDS | MUTE_KEYWORDS:
                assert h.matches(kw) is False, f"vol kw {kw!r} matched without audio"

    def test_match_when_audio_available(self):
        h = SystemControlsHandler()
        with patch.object(h, "_audio_available", return_value=True):
            for kw in VOLUME_KEYWORDS | MUTE_KEYWORDS:
                assert h.matches(kw) is True, f"vol kw {kw!r} did not match with audio"

    def test_no_match_when_backlight_unavailable(self):
        h = SystemControlsHandler()
        with patch.object(h, "_backlight_available", return_value=False):
            for kw in BRIGHTNESS_KEYWORDS:
                assert h.matches(kw) is False, f"brightness kw {kw!r} matched without backlight"

    def test_match_when_backlight_available(self):
        h = SystemControlsHandler()
        with patch.object(h, "_backlight_available", return_value=True):
            for kw in BRIGHTNESS_KEYWORDS:
                assert h.matches(kw) is True, f"brightness kw {kw!r} did not match with backlight"

    def test_no_match_for_unrelated_query(self):
        h = SystemControlsHandler()
        with patch.object(h, "_audio_available", return_value=True), \
             patch.object(h, "_backlight_available", return_value=True):
            assert h.matches("firefox") is False
            assert h.matches("= 1+1") is False
            assert h.matches("") is False

    def test_partial_keyword_does_not_match(self):
        """matches() compares whole-string equality, not substring."""
        h = SystemControlsHandler()
        with patch.object(h, "_audio_available", return_value=True):
            assert h.matches("vol level") is False  # only exact "vol" matches
            assert h.matches("volu") is False


class TestGetResults:
    """get_results() returns ResultItems with widget_builder callbacks."""

    def test_volume_keyword_returns_volume_result(self):
        h = SystemControlsHandler()
        with patch.object(h, "_audio_available", return_value=True):
            results = h.get_results("vol")
        assert len(results) == 1
        assert results[0].title == "Volume"
        assert results[0].result_type == "control"
        assert callable(results[0].widget_builder)

    def test_brightness_keyword_returns_brightness_result(self):
        h = SystemControlsHandler()
        with patch.object(h, "_backlight_available", return_value=True):
            results = h.get_results("brightness")
        assert len(results) == 1
        assert results[0].title == "Brightness"
        assert callable(results[0].widget_builder)

    def test_unknown_query_returns_empty(self):
        h = SystemControlsHandler()
        results = h.get_results("nonsense")
        assert results == []


class TestServiceAvailabilityGuards:
    """The HAS_AUDIO / HAS_BACKLIGHT module-level flags + try/except shape.

    AudioService and BacklightService are only imported into the controls
    module's namespace when HAS_AUDIO/HAS_BACKLIGHT are True (the conditional
    import succeeds). On a headless test box, the imports fail and those
    names don't exist on the module — so we use monkeypatch with
    raising=False to inject them.
    """

    def test_audio_unavailable_when_get_default_raises(self, monkeypatch):
        import search.handlers.controls as m

        mock_svc = MagicMock()
        mock_svc.get_default.side_effect = RuntimeError("no audio service")
        monkeypatch.setattr(m, "HAS_AUDIO", True, raising=False)
        monkeypatch.setattr(m, "AudioService", mock_svc, raising=False)

        assert SystemControlsHandler()._audio_available() is False

    def test_audio_available_when_get_default_returns(self, monkeypatch):
        import search.handlers.controls as m

        mock_svc = MagicMock()
        mock_svc.get_default.return_value = MagicMock()
        monkeypatch.setattr(m, "HAS_AUDIO", True, raising=False)
        monkeypatch.setattr(m, "AudioService", mock_svc, raising=False)

        assert SystemControlsHandler()._audio_available() is True

    def test_backlight_unavailable_when_service_reports_unavailable(self, monkeypatch):
        import search.handlers.controls as m

        svc = MagicMock()
        svc.available = False
        mock_svc = MagicMock()
        mock_svc.get_default.return_value = svc
        monkeypatch.setattr(m, "HAS_BACKLIGHT", True, raising=False)
        monkeypatch.setattr(m, "BacklightService", mock_svc, raising=False)

        assert SystemControlsHandler()._backlight_available() is False

    def test_backlight_available_when_service_reports_available(self, monkeypatch):
        import search.handlers.controls as m

        svc = MagicMock()
        svc.available = True
        mock_svc = MagicMock()
        mock_svc.get_default.return_value = svc
        monkeypatch.setattr(m, "HAS_BACKLIGHT", True, raising=False)
        monkeypatch.setattr(m, "BacklightService", mock_svc, raising=False)

        assert SystemControlsHandler()._backlight_available() is True
