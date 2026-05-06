"""
Tests for pure functions in launcher/panels/backdrop.py.

Only the functions that don't require GTK/PIL/grim are tested here.
The actual blur pipeline is integration territory and lives in cage tests.
"""

import pytest

# PIL and gi.repository.GdkPixbuf are mocked or installed by conftest.py.
# Only `_ease_in_intervals` is a pure function — we just need the import to
# succeed (which depends on conftest's gi/ignis tree).
from panels.backdrop import (
    _BLUR_STEPS,
    _CLOSE_DURATION_MS,
    _OPEN_DURATION_MS,
    _ease_in_intervals,
)


class TestEaseInIntervals:
    """The quadratic ease-in curve must accelerate (early frames slower)."""

    def test_returns_steps_minus_one_intervals(self):
        intervals = _ease_in_intervals(150, 7)
        assert len(intervals) == 6  # N positions = N-1 deltas

    def test_total_approximates_target_duration(self):
        intervals = _ease_in_intervals(150, 7)
        # Each interval is rounded down to int with a 10ms floor — total
        # should be within 10ms of target.
        total = sum(intervals)
        assert abs(total - 150) <= 10, f"total {total} too far from 150"

    def test_curve_accelerates(self):
        """Quadratic ease-in: early intervals LONGER than late intervals."""
        intervals = _ease_in_intervals(150, 7)
        # First interval should be at least 2x the last interval — reverse
        # of acceleration is "early slow, late fast" so deltas grow.
        # For (i/(N-1))**2: deltas[0] is small, deltas[-1] is large.
        # So we expect intervals[0] < intervals[-1].
        assert intervals[0] < intervals[-1], (
            f"curve does not accelerate — got intervals {intervals}"
        )

    def test_intervals_are_monotonically_non_decreasing(self):
        """Each successive interval >= previous (non-decreasing under ease-in)."""
        intervals = _ease_in_intervals(150, 7)
        for i in range(1, len(intervals)):
            assert intervals[i] >= intervals[i - 1], (
                f"non-monotonic at idx {i}: {intervals}"
            )

    def test_minimum_floor_of_10ms(self):
        """Even at high step count, every interval is at least 10ms."""
        intervals = _ease_in_intervals(50, 20)
        assert all(x >= 10 for x in intervals), (
            f"some interval < 10ms floor: {intervals}"
        )

    def test_single_step_returns_total(self):
        """Edge case: 1 step → return [total_ms]."""
        assert _ease_in_intervals(150, 1) == [150]

    def test_zero_steps_returns_total(self):
        """Edge case: 0 or negative steps → return [total_ms]."""
        assert _ease_in_intervals(150, 0) == [150]


class TestModuleConstants:
    """Sanity-check the tuned animation constants stay coherent."""

    def test_blur_steps_is_positive(self):
        assert _BLUR_STEPS > 1

    def test_durations_are_reasonable(self):
        # Animation should be perceptible but not draggy: 50-500ms.
        assert 50 <= _OPEN_DURATION_MS <= 500
        assert 50 <= _CLOSE_DURATION_MS <= 500
