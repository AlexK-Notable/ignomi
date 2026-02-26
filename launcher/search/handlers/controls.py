"""
System Controls Handler - Inline volume and brightness controls.

Triggers on keywords like "vol", "volume", "bright", "brightness", "mute".
Renders Scale and Switch widgets directly in search results using
Ignis AudioService and BacklightService.
"""

from search.router import ResultItem

from ignis import widgets

# Audio may not be available without ignis-gvc
try:
    from ignis.services.audio import AudioService
    HAS_AUDIO = True
except Exception:
    HAS_AUDIO = False

try:
    from ignis.services.backlight import BacklightService
    HAS_BACKLIGHT = True
except Exception:
    HAS_BACKLIGHT = False


VOLUME_KEYWORDS = {"vol", "volume", "sound", "audio", "speaker"}
BRIGHTNESS_KEYWORDS = {"bright", "brightness", "backlight", "screen"}
MUTE_KEYWORDS = {"mute", "unmute"}


class SystemControlsHandler:
    """Show inline system controls for volume and brightness."""

    name = "controls"
    priority = 50  # Highest priority — check before everything

    def _audio_available(self) -> bool:
        """Check if audio control is actually usable."""
        if not HAS_AUDIO:
            return False
        try:
            AudioService.get_default()
            return True
        except Exception:
            return False

    def _backlight_available(self) -> bool:
        """Check if backlight control is actually usable."""
        if not HAS_BACKLIGHT:
            return False
        try:
            return BacklightService.get_default().available
        except Exception:
            return False

    def matches(self, query: str) -> bool:
        q = query.strip().lower()
        if q in VOLUME_KEYWORDS or q in MUTE_KEYWORDS:
            return self._audio_available()
        if q in BRIGHTNESS_KEYWORDS:
            return self._backlight_available()
        return False

    def get_results(self, query: str) -> list[ResultItem]:
        q = query.strip().lower()
        results = []

        if q in VOLUME_KEYWORDS or q in MUTE_KEYWORDS:
            results.append(ResultItem(
                title="Volume",
                icon="audio-volume-high",
                result_type="control",
                widget_builder=self._build_volume_control,
            ))

        if q in BRIGHTNESS_KEYWORDS:
            results.append(ResultItem(
                title="Brightness",
                icon="display-brightness",
                result_type="control",
                widget_builder=self._build_brightness_control,
            ))

        return results

    def _build_volume_control(self):
        """Build inline volume control with slider and mute toggle."""
        audio = AudioService.get_default()
        speaker = audio.speaker

        volume_label = widgets.Label(
            label=f"{int(speaker.volume)}%",
            css_classes=["control-value"],
        )

        def on_volume_change(scale):
            speaker.volume = scale.value
            volume_label.set_label(f"{int(scale.value)}%")

        def on_mute_toggle(switch, active):
            speaker.is_muted = not active

        volume_scale = widgets.Scale(
            min=0, max=100, step=1,
            value=speaker.volume,
            hexpand=True,
            css_classes=["control-scale"],
            on_change=on_volume_change,
        )

        mute_switch = widgets.Switch(
            active=not speaker.is_muted,
            css_classes=["control-switch"],
            on_change=on_mute_toggle,
        )

        return widgets.Box(
            css_classes=["control-row", "result-item"],
            spacing=12,
            child=[
                widgets.Icon(
                    image="audio-volume-high",
                    pixel_size=24,
                    css_classes=["control-icon"],
                ),
                widgets.Label(
                    label="Volume",
                    css_classes=["control-label"],
                ),
                volume_scale,
                volume_label,
                mute_switch,
            ]
        )

    def _build_brightness_control(self):
        """Build inline brightness control with slider."""
        backlight = BacklightService.get_default()

        brightness_pct = int(backlight.brightness / backlight.max_brightness * 100) \
            if backlight.max_brightness > 0 else 0

        brightness_label = widgets.Label(
            label=f"{brightness_pct}%",
            css_classes=["control-value"],
        )

        def on_brightness_change(scale):
            raw_value = int(scale.value / 100 * backlight.max_brightness)
            backlight.brightness = raw_value
            brightness_label.set_label(f"{int(scale.value)}%")

        brightness_scale = widgets.Scale(
            min=1, max=100, step=1,
            value=brightness_pct,
            hexpand=True,
            css_classes=["control-scale"],
            on_change=on_brightness_change,
        )

        return widgets.Box(
            css_classes=["control-row", "result-item"],
            spacing=12,
            child=[
                widgets.Icon(
                    image="display-brightness-symbolic",
                    pixel_size=24,
                    css_classes=["control-icon"],
                ),
                widgets.Label(
                    label="Brightness",
                    css_classes=["control-label"],
                ),
                brightness_scale,
                brightness_label,
            ]
        )
