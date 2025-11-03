# Ignomi Launcher - UI Design Philosophy

**Last Updated:** 2025-11-02
**Status:** Phase 1 - Basic Transparency + Blur (In Progress)

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
- **App icons** (`.app-icon`) - 32px (search) / 48px (side panels)
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

**Usage Plan:**
- Hover states: `@color4` or `@color5`
- Active states: `@color6`
- Subtle backgrounds: `alpha(@color1, 0.3)`
- Borders: `alpha(@color4, 0.5)`

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

### Target Aesthetic

**Transparency Levels:**
- Panel containers: **70-80%** opacity (more transparent than Waybar for launcher context)
- Search entry: **60%** background, **80%** on focus
- App items: **Transparent** background, **25%** accent on hover
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

```css
.panel {
    background: linear-gradient(
        to bottom,
        alpha(@bg, 0.85) 0%,
        alpha(@bg, 0.70) 40%,
        alpha(@bg, 0.40) 70%,
        alpha(@bg, 0.10) 100%
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

### Phase 1: Basic Transparency + Blur ⭐ **START HERE**

**Goal:** Get blur working and improve transparency to match system aesthetic

**Tasks:**
1. Add Hyprland layerrule: `layerrule = blur, ignomi` (in windowrules.conf)
2. Reduce panel opacity: `alpha(@bg, 0.95)` → `alpha(@bg, 0.75)`
3. Add panel borders: `border: 1px solid alpha(@accent, 0.3)`
4. Add panel shadows: `box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4)`
5. Test on multiple wallpapers for readability

**Success Criteria:**
- Blur visible behind panels
- Can see wallpaper through panels but text remains readable
- Visual consistency with Waybar

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

GTK supports `alpha()` for transparency:
```css
background-color: alpha(@bg, 0.75);  /* 75% opacity */
```

For gradients, need to specify RGBA:
```css
background: linear-gradient(to bottom,
    rgba(16, 16, 16, 0.85),  /* @bg at 85% */
    rgba(16, 16, 16, 0.10)   /* @bg at 10% */
);
```

**Challenge:** Can't directly use Wallust variables in gradients - need to generate them via template.

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

### Future Updates
- Phase 1 completion notes
- Screenshots before/after
- User feedback integration
- Performance measurements
