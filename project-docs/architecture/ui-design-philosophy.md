# Ignomi Launcher - UI Design Philosophy

**Last Updated:** 2026-02-23
**Status:** Phase 1 Complete (2025-11-02). Phase 2+ not yet started.

## Design Vision

Create a modern, translucent launcher that seamlessly integrates with the Wallust-based color scheme while maintaining excellent readability and usability. The aesthetic should match other themed components in the system (Waybar, Wofi) with blur, transparency, and dynamic color accents.

---

## Current UI Component Inventory

### Three-Panel Architecture

1. **Bookmarks Panel (Left)**
   - User-curated favorite applications
   - Drag-and-drop reordering
   - Right-click to remove
   - Panel header: "Bookmarks"
   - App list with icons + labels

2. **Search Panel (Center)**
   - Real-time application search
   - Search entry field
   - Filtered results list (top 30)
   - Right-click to add to bookmarks
   - Escape key to close

3. **Frequent Panel (Right)**
   - Frecency-ranked applications
   - Usage count badges
   - Auto-updates on app launch
   - Right-click to bookmark
   - Panel header: "Frequent"

### Styled Components

- **Panel containers** (`.panel`) - main container for each panel
- **Panel headers** (`.panel-header`) - "Bookmarks" / "Frequent" titles
- **App items** (`.app-item`) - clickable app buttons
- **App icons** (`.app-icon`) - 24px (search results) / 48px (bookmarks + frequent panels)
- **App text**:
  - `.app-name` - primary app name (14px, bold)
  - `.app-description` - secondary description (11px)
  - `.frecency-count` - usage statistics (10px, italic)
- **Search entry** (`.search-entry`) - text input field
- **Scrollbars** - custom styled for all panels
- **Drag indicators** (`.drag-hover`) - visual feedback for DnD

---

## Color Integration Strategy

### Wallust Color Variables (Already Integrated)

From `/home/komi/repos/ignomi/launcher/styles/colors.css`:

- `@bg` - Background color from wallpaper
- `@fg` - Foreground/text color
- `@accent` - Primary accent color
- `@success` - Success state color
- `@warning` - Warning state color
- `@error` - Error state color

### Extended Palette (To Be Integrated)

Wallust generates `@color0` through `@color15` for expanded theming:

- `@color1-3` - Dark shades
- `@color4-6` - Mid tones (good for accents)
- `@color7-8` - Light tones (good for hover states)
- `@color9-15` - Vibrant variants

**Implemented Usage (pre-computed alpha variants in Wallust template):**
- Hover states: `@color4_30` (30% opacity color4)
- Active states: `@color6_50` (50% opacity color6)
- Keyboard selection: `@color6_40` with `@color6` left border
- Search focus glow: `@color6_30`
- Borders: `@color4_40` (search entry), `@accent` (drag indicator)
- Scrollbar: `@color4_40` default, `@color6_60` hover

---

## Transparency & Blur Philosophy

### Inspiration: Waybar Island Design

From `~/.config/waybar/style.css`:
```css
.modules-left,
.modules-center,
.modules-right {
    background: rgba(35, 25, 23, 0.85);  /* 85% opacity */
    border: 1px solid rgba(182, 115, 88, 0.3);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    border-radius: 14px;
}
```

### Implemented Aesthetic

**Transparency Levels (actual, using pre-computed Wallust alpha variants):**
- Panel containers (`.panel`): **65% opacity** (`@bg_65`) -- more transparent than Waybar
- Search entry (`.search-entry`): **60%** background (`@bg_60`), **80%** on focus (`@bg_80`)
- App items: **Transparent** background, **30%** color4 on hover (`@color4_30`)
- Active state: **50%** color6 (`@color6_50`)
- Headers: **Inherit** from panel

**Blur Settings:**
Hyprland global blur (from `decorations.conf`):
- Size: 15
- Passes: 2
- Enable via layerrule for launcher

**Why Blur Matters:**
- Maintains readability over busy wallpapers
- Creates depth and visual hierarchy
- Modern aesthetic consistency with other system components

---

## Border & Shadow Strategy

### Borders

**Current:** Minimal borders
**Target:**
- Panel containers: 1px solid with `alpha(@accent, 0.3)` - subtle outline
- Search entry: 1px solid, changes to `@accent` on focus
- No borders on individual app items (keeps clean look)

### Shadows

**Current:** None
**Target:**
- Panel containers: `box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4)`
- Creates floating effect
- Adds depth separation from wallpaper background
- Consistent with Waybar island design

---

## Animation Philosophy

### Current Animations

- App item hover: `transition: all 0.15s ease` + `translateX(2px)`
- App item active: `scale(0.98)`
- Bookmark pulse: `@keyframes bookmark-pulse` (0.3s)

### Planned Animations

**Panel Entry/Exit:**
- Slide animation for panels (like Waybar's `layerrule = animation slide down`)
- Options:
  - Left panel: slide from left
  - Center panel: slide from top (or fade in)
  - Right panel: slide from right
- Duration: 200-300ms
- Easing: `cubic-bezier(0.4, 0.0, 0.2, 1)` - material design standard

**Search Entry:**
- Smooth border color transition on focus (0.2s)
- Subtle scale up on focus (1.02x)?

**App Items:**
- Current translateX is good, keep it
- Consider adding subtle background fade

---

## Typography Hierarchy

### Current Setup

- **Headers:** 16px, bold
- **App names:** 14px, semi-bold (600)
- **Descriptions:** 11px, regular (70% opacity)
- **Usage counts:** 10px, italic (50% opacity)
- **Search entry:** 16px

### Font Family

From Waybar: `"JetBrains Mono", "Fira Sans Semibold", "Font Awesome 6 Free"`

**Recommendation:** Use same font stack for consistency

---

## Gradient Vision (Phase 4 - Future)

### Vertical Panel Gradients

**Concept:** Solid color at top fading to transparent at bottom

> Note: Would require additional pre-computed alpha variants in the Wallust
> template since `alpha(@bg, N)` does not work at runtime in GTK4.

```css
/* Would need @bg_85, @bg_70, @bg_40, @bg_10 pre-computed in colors.css */
.panel {
    background: linear-gradient(
        to bottom,
        @bg_85 0%,
        @bg_70 40%,
        @bg_40 70%,
        @bg_10 100%
    );
}
```

**Benefits:**
- Creates visual "weight" at top (where headers are)
- Lighter bottom reduces visual clutter
- Natural eye flow from header → content

**Challenges:**
- May reduce readability for bottom items
- Need to test with different wallpapers
- Scrollbar visibility concerns

**Alternative:** Subtle accent gradient overlay instead of opacity gradient

---

## Implementation Phases

### Phase 1: Basic Transparency + Blur -- COMPLETE (2025-11-02, commit 2968990)

**Implemented:**
1. Hyprland layerrules configured for blur and per-panel slide animations
2. Panel opacity set to 65% (`@bg_65`) -- lower than originally planned 75%
3. Borders removed in favor of clean borderless design (`border: none`)
4. Shadows removed (`box-shadow: none`) -- the blur provides sufficient depth
5. Window-level `background: transparent` discovered as critical requirement for GTK4 Layer Shell
6. Pre-computed 16 alpha variants in Wallust template (GTK4 `alpha(@var)` limitation)

**Divergences from original plan:**
- Opacity went to 65% (not 75%) for more translucent look
- Panel borders and shadows were removed after testing -- the minimalist look was preferred
- CSS uses `@bg_65` pre-computed variables, not `alpha(@bg, 0.65)` (GTK4 limitation)

### Phase 2: Enhanced Wallust Integration

**Goal:** Use full Wallust color palette for richer theming

**Tasks:**
1. Import extended palette (@color0-15) to colors.css template
2. Update hover states to use `@color4`/`@color5`
3. Update active states to use `@color6`
4. Improve search entry focus state with vibrant accent
5. Theme scrollbars with Wallust colors

**Success Criteria:**
- Dynamic colors that change with wallpaper
- Better visual feedback on interactions
- Cohesive color story across all elements

### Phase 3: Visual Polish

**Goal:** Smooth animations and refined interactions

**Tasks:**
1. Add panel slide-in animations via Hyprland layerrule
2. Improve app item transitions
3. Add subtle scale/glow effects on focus
4. Refine scrollbar styling
5. Typography adjustments if needed

**Success Criteria:**
- Buttery smooth interactions
- Polished feel comparable to commercial launchers
- Delightful micro-interactions

### Phase 4: Gradients (Future Enhancement)

**Goal:** Vertical gradients for visual sophistication

**Tasks:**
1. Experiment with gradient backgrounds
2. Test readability across different wallpapers
3. Implement if it enhances aesthetic without reducing usability
4. Consider gradient overlays vs opacity gradients

**Success Criteria:**
- Maintains readability
- Enhances visual hierarchy
- Doesn't distract from content

---

## Design Principles

### 1. Readability First
No amount of visual flair should compromise text legibility. Always test on:
- Dark wallpapers
- Light wallpapers
- Busy/high-contrast wallpapers

### 2. Consistency with System
Match the aesthetic of:
- Waybar (transparency, blur, island design)
- Hyprland decorations (blur, shadows)
- Other Wallust-themed components

### 3. Performance Awareness
- Blur is GPU-intensive (Hyprland handles it)
- Animations should be smooth (hardware accelerated)
- Keep CSS simple and efficient

### 4. Accessibility
- Sufficient color contrast
- Clear focus indicators
- Keyboard navigation support (already implemented)

### 5. Wallust-First Design
The launcher should **enhance** wallpapers, not compete with them. Use wallpaper colors to create harmony, not clash.

---

## Technical Notes

### Hyprland Layer Rules

Layer-shell applications (Ignis) require layerrule configuration in Hyprland:

```conf
# In ~/.config/hypr/config/windowrules.conf
layerrule = blur, ^(ignomi-.*)$
layerrule = animation slide top, ^(ignomi-search)$
layerrule = animation slide left, ^(ignomi-bookmarks)$
layerrule = animation slide right, ^(ignomi-frequent)$
```

**Note:** Match by namespace, not window class (Ignis windows report as "python")

### GTK4 CSS Limitations

- No backdrop-filter (Hyprland blur handles this)
- Limited gradient support on some properties
- Shadow performance varies

### CSS Color Functions

**Critical GTK4 limitation discovered during Phase 1:**

GTK4's `alpha()` function works with literal hex values but **does NOT work** with `@define-color` variables:
```css
/* DOES NOT WORK -- @bg resolves at parse time, alpha() fails */
background-color: alpha(@bg, 0.75);

/* WORKS -- pre-compute in Wallust template with literal hex */
@define-color bg_75 alpha(#292420, 0.75);
background-color: @bg_75;
```

All alpha variants must be pre-computed in the Wallust template (`~/.config/wallust/templates/ignomi.css`) using literal `{{background}}` / `{{colorN}}` template variables that resolve to hex values before GTK4 parses them.

See `project-docs/research/gtk4-layer-shell-transparency.md` for full details.

---

## Inspiration References

### Similar Launchers

- **Wofi** - Simple blur + transparency
- **Walker** - Modern design, good use of space
- **Rofi (Wayland)** - Classic, functional

### System Components

- **Waybar** - Our primary aesthetic reference
  - Island design with blur
  - ~85% opacity
  - Subtle borders and shadows
  - Clean, modern look

### Design Systems

- **Material Design** - Animation curves, elevation
- **Fluent Design** - Acrylic blur effects
- **macOS Big Sur** - Translucent panels

---

## Open Questions / Future Considerations

1. **Gradient Implementation:**
   - CSS gradients or PNG overlays?
   - Dynamic gradients based on wallpaper brightness?

2. **Border Radius:**
   - Current: 12px (panels), 8px (items)
   - Should we match Waybar's 14px?

3. **Panel Width:**
   - Current: 320px (sides), 600px (center)
   - Should side panels be narrower for more screen space?

4. **Animation Direction:**
   - Should all panels slide from their respective edges?
   - Or unified animation (all fade, or all from top)?

5. **Dark Mode Variants:**
   - Should we have light/dark presets?
   - Or pure Wallust-driven (no manual overrides)?

6. **Performance:**
   - How many blur passes before it's too heavy?
   - Should blur be configurable via settings.toml?

---

## Change Log

### 2025-11-02 - Initial Document
- Created comprehensive UI design philosophy
- Documented current state
- Planned 4-phase implementation
- Identified all UI components and styling elements
- Established design principles

### 2026-02-23 - Accuracy Update
- Updated status: Phase 1 marked complete (was "In Progress")
- Fixed icon sizes: search icons are 24px, not 32px
- Fixed opacity values: panels use 65% (`@bg_65`), not 75%
- Fixed CSS examples: replaced `alpha(@var, N)` patterns with pre-computed variables
- Added GTK4 `alpha()` limitation documentation
- Updated Phase 1 section with actual implementation details and divergences
