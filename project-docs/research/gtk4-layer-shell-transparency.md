# GTK4 Layer Shell Transparency Research

**Date**: 2025-11-02
**Context**: Ignomi launcher Phase 1 theming implementation
**Status**: SOLVED

## Problem Statement

GTK4 Layer Shell windows (used for Wayland desktop widgets) require special handling to support transparency and compositor blur effects. Child widget RGBA backgrounds remain opaque even with correct alpha values unless the window itself is explicitly configured for transparency.

## Root Cause

GTK4's rendering model for Layer Shell windows defaults to opaque window surfaces. When a Layer Shell window is created without explicit transparency, the compositor treats it as a solid surface regardless of CSS styling on child widgets.

### Technical Details

- **Layer Shell Protocol**: Wayland's `zwlr_layer_shell_v1` protocol for desktop shell components
- **GTK4 Rendering**: Uses window-level surface properties to determine compositing behavior
- **CSS Limitation**: Child widget styles (`background-color: rgba(...)`) cannot override window-level opacity
- **Compositor Dependency**: Blur effects require transparent surfaces to blend correctly

## The Solution

Add this CSS rule to enable transparency:

```css
window {
    background: transparent;
}
```

### Why This Works

1. **Surface-Level Configuration**: Sets the window's rendering surface to support alpha channel
2. **Compositor Handshake**: Signals to Wayland compositor that this window participates in blending
3. **Enables Blur**: Transparent surfaces can be blurred by compositor (Hyprland's `layerrule = blur`)
4. **Child Inheritance**: Once window transparency is enabled, child widget RGBA values work correctly

## Investigation Process

### Failed Attempts

1. **Inline alpha() function**: `background-color: alpha(@bg, 0.75)`
   - Issue: GTK4 CSS parser cannot use `@define-color` variables inside `alpha()` function
   - Solution: Pre-compute alpha variants in Wallust template

2. **Wallust template variables**: Used `{{accent}}` and `{{success}}`
   - Issue: Wallust only provides `{{background}}`, `{{foreground}}`, `{{color0-15}}`
   - Solution: Map to correct color indices (`{{color3}}` for accent, `{{color2}}` for success)

3. **Child widget styling only**: Applied RGBA to `.panel` class without window transparency
   - Issue: Window surface remained opaque, blocking all transparency
   - Solution: Added `window { background: transparent; }`

### Diagnostic Process

1. **Test with literal colors**: Replaced Wallust variables with `rgba(2, 0, 0, 0.75)`
   - Result: Red appeared, proving CSS was loading correctly
   - Conclusion: Template variables were broken, but transparency still needed fixing

2. **Fixed template variables**: Changed to proper Wallust color indices
   - Result: No CSS parsing errors, but still no transparency
   - Conclusion: Separate issue with Layer Shell window configuration

3. **Research GTK4 documentation**: Found references to "windowing system capabilities"
   - Quote: "Applying opacity depends on the capabilities of the windowing system"
   - Pattern: Waybar and other working apps use `window { background: transparent; }`

4. **Applied window-level transparency**: Added CSS rule
   - Result: Immediate success - transparency and blur both working
   - Confirmation: This is the required pattern for GTK4 Layer Shell apps

## Evidence and Patterns

### Working Examples

All GTK4 Wayland apps with transparency use this pattern:

- **Waybar**: `window#waybar { background: transparent; }`
- **GTK4 Layer Shell Demo**: Sets window background to transparent in CSS
- **Other desktop widgets**: Consistent pattern across ecosystem

### Technical References

- GTK4 documentation on window opacity
- Layer Shell protocol specification
- Hyprland compositor blur implementation
- Wayland compositing model

## Lessons Learned

### Critical Insights

1. **Window vs Widget Styling**: Surface-level properties (window) vs content styling (widgets) are separate concerns
2. **Compositor Requirements**: Blur effects require transparent surfaces at window level
3. **CSS Hierarchy**: Window transparency is prerequisite for child widget RGBA to function
4. **Pattern Recognition**: Working examples (Waybar) provide reliable templates

### GTK4 CSS Limitations

Discovered during this investigation:

1. **No variable alpha()**: Cannot use `alpha(@variable, number)` with `@define-color` variables
2. **Pre-computation required**: All alpha variants must be computed in Wallust template
3. **Parse-time resolution**: GTK4 resolves CSS variables at parse time, not runtime

Example Wallust template pattern:

```css
/* Pre-computed alpha variants (GTK4 doesn't support alpha(@var, num)) */
@define-color bg_75 alpha({{background}}, 0.75);
@define-color bg_60 alpha({{background}}, 0.60);
@define-color fg_70 alpha({{foreground}}, 0.70);
@define-color accent_30 alpha({{color3}}, 0.30);
```

### Wallust Template Variables

Wallust provides these template variables (NOT `{{accent}}` or `{{success}}`):

- `{{background}}` - Dark/light base background color
- `{{foreground}}` - Contrasting text color
- `{{color0}}` through `{{color15}}` - 16-color palette from wallpaper
- `{{cursor}}` - Cursor accent color

For semantic naming, map color indices:
- `{{color3}}` → accent (typically yellow/orange from wallpaper)
- `{{color2}}` → success (typically green from wallpaper)
- `{{color1}}` → error/warning (typically red from wallpaper)

## Implementation Checklist

For any GTK4 Layer Shell app with transparency:

- [ ] Set window background to transparent in CSS: `window { background: transparent; }`
- [ ] Pre-compute all alpha variants in color template (no inline `alpha(@var, num)`)
- [ ] Use correct Wallust template variable names (`{{colorN}}` not `{{semantic}}`)
- [ ] Configure compositor blur rules (e.g., `layerrule = blur, namespace`)
- [ ] Test with diagnostic literal colors first to isolate issues
- [ ] Verify compositor supports blur on layer-shell surfaces

## Related Files

- `/home/komi/repos/ignomi/launcher/styles/main.css` - Window transparency CSS
- `/home/komi/.config/wallust/templates/ignomi.css` - Wallust color template
- `/home/komi/.config/hypr/config/windowrules.conf` - Compositor blur configuration
- `/home/komi/repos/ignomi/launcher/styles/colors.css` - Generated color definitions

## References

- Ignis Framework: https://ignis-sh.github.io/
- GTK4 CSS documentation
- Wayland Layer Shell protocol
- Hyprland layer rules documentation

## Status

**RESOLVED** - Pattern documented, implementation successful, transparency and blur fully functional across all three monitor setup.
