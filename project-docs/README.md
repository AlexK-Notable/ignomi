# Ignomi Project Documentation

This directory contains comprehensive project documentation organized by type and purpose.

## Directory Structure

### `architecture/`
Design and architectural documentation for the Ignomi launcher.

- **2025-11-02-ignomi-launcher-design.md** - Original comprehensive design document
  - Project overview and motivation
  - Three-panel architecture (bookmarks/search/frequent)
  - Frecency algorithm design
  - Technology choices (Ignis, GTK4, Wayland)
  - Implementation phases

- **ui-design-philosophy.md** - UI component inventory and design philosophy
  - Complete component breakdown per panel
  - Styling priorities and visual hierarchy
  - Color and transparency strategy
  - Animation philosophy
  - Technical notes on GTK4 and Wallust integration

### `research/`
Technical research, investigations, and deep dives into specific technologies or problems.

- **gtk4-layer-shell-transparency.md** - GTK4 Layer Shell transparency research
  - Root cause analysis of transparency requirements
  - Window vs widget styling hierarchy
  - GTK4 CSS limitations (alpha function, variable resolution)
  - Wallust template variable reference
  - Implementation checklist for future GTK4 Layer Shell apps
  - Working examples and patterns

### `discoveries/`
Lessons learned, debugging experiences, and insights from development.

- **systematic-debugging-phase1-theming.md** - Phase 1 theming debugging process
  - Complete timeline of issue investigation
  - Systematic debugging methodology applied
  - Key discoveries and breakthroughs
  - Do's and don'ts for future debugging
  - Code changes and their rationale
  - User feedback progression

### `status/`
Project status updates, milestone completions, and progress tracking.

- **2025-11-02-phase1-complete.md** - Phase 1 theming completion status
  - All 12 completed tasks
  - Technical achievements summary
  - File changes and git commit details
  - Success metrics (before/after)
  - Next steps for Phase 2+
  - Lessons for future development

## Documentation Philosophy

### Why Organized This Way

1. **Post-Compaction Reference**: Session context gets lost after compaction. Comprehensive documentation preserves critical discoveries and context.

2. **Knowledge Transfer**: Future sessions (or other developers) can quickly understand:
   - What was built (architecture)
   - What was learned (research)
   - How problems were solved (discoveries)
   - What's been completed (status)

3. **Pattern Recognition**: Research documents capture reusable patterns that apply beyond this specific project (e.g., GTK4 Layer Shell transparency applies to all desktop widgets).

4. **Debugging Reference**: Systematic debugging documentation helps avoid repeating solved problems.

## How to Use This Documentation

### For New Development
1. Start with `architecture/` to understand the overall design
2. Check `status/` for current progress and next steps
3. Review `research/` for technical constraints and patterns
4. Learn from `discoveries/` to avoid known pitfalls

### For Debugging
1. Check `discoveries/` for similar past issues
2. Review `research/` for known limitations
3. Apply systematic debugging methodology
4. Document new discoveries for future reference

### For Contributing
1. Read architecture documents to understand design decisions
2. Check status updates for current state
3. Add new discoveries to appropriate directories
4. Update status documents when completing milestones

## Key Discoveries

### Critical Patterns (Must Know)

1. **GTK4 Layer Shell Transparency** (research/gtk4-layer-shell-transparency.md)
   - REQUIRED: `window { background: transparent; }` in CSS
   - Applies to ALL GTK4 Layer Shell applications
   - Not documented in Ignis framework guides

2. **GTK4 CSS Limitations** (research/gtk4-layer-shell-transparency.md)
   - Cannot use `alpha(@variable, number)` with `@define-color` variables
   - Must pre-compute alpha variants in Wallust template
   - Variables resolve at parse time, not runtime

3. **Wallust Template Variables** (research/gtk4-layer-shell-transparency.md)
   - Provides: `{{background}}`, `{{foreground}}`, `{{color0-15}}`
   - Does NOT provide: `{{accent}}`, `{{success}}`, etc.
   - Map semantic names to color indices in template

4. **Systematic Debugging** (discoveries/systematic-debugging-phase1-theming.md)
   - Change one variable at a time
   - Use diagnostic tests with known-good values
   - Layer from bottom up (CSS loading → variables → transparency)
   - Compare with working examples
   - Document evidence at each step

## Documentation Standards

When adding new documentation:

### Choose the Right Directory

- **architecture/** - Design decisions, component structure, system architecture
- **research/** - Technical investigations, library limitations, pattern discoveries
- **discoveries/** - Debugging processes, lessons learned, insights from development
- **status/** - Milestone completion, progress updates, next steps

### Include These Sections

1. **Date** - When was this documented
2. **Context** - What prompted this documentation
3. **Status** - Current state (e.g., COMPLETE, IN PROGRESS, BLOCKED)
4. **Key Findings** - Most important takeaways
5. **Related Files** - Code locations affected
6. **References** - External documentation or examples

### Cross-Reference

Link related documents:
- Architecture documents reference research for technical justifications
- Discoveries reference architecture for context
- Status updates reference all relevant documentation
- Research documents stand alone but link to implementations

## Maintenance

### When to Update

1. **Architecture** - When design changes or new components added
2. **Research** - When new technical limitations or patterns discovered
3. **Discoveries** - After significant debugging sessions or insights
4. **Status** - After completing milestones or phases

### Keep It Current

- Archive outdated documents with date prefixes
- Update cross-references when moving files
- Add new discoveries immediately (context fades fast)
- Link git commits to relevant documentation

## Contributing Upstream

Some discoveries should be contributed back to upstream projects:

1. **Ignis Framework** - GTK4 Layer Shell transparency requirement
2. **Wallust** - Template variable reference documentation
3. **GTK4 Documentation** - CSS parser limitations with variables

These contributions help the entire ecosystem and prevent others from hitting the same undocumented issues.

## Quick Reference

### Most Important Documents

1. **GTK4 transparency pattern**: `research/gtk4-layer-shell-transparency.md`
2. **Debugging methodology**: `discoveries/systematic-debugging-phase1-theming.md`
3. **Current status**: `status/2025-11-02-phase1-complete.md`
4. **Overall design**: `architecture/2025-11-02-ignomi-launcher-design.md`

### Common Questions

**Q: Why isn't transparency working?**
→ See `research/gtk4-layer-shell-transparency.md` for window-level transparency requirement

**Q: Why don't Wallust variables work?**
→ See `research/gtk4-layer-shell-transparency.md` section on template variable names

**Q: How should I debug issues?**
→ See `discoveries/systematic-debugging-phase1-theming.md` for methodology

**Q: What's the current state of the project?**
→ See latest document in `status/` directory

## Future Documentation

As the project evolves, add:

- Performance profiling results (research/)
- Animation system design (architecture/)
- User feedback and UX insights (discoveries/)
- Phase 2+ completion status (status/)
- Integration patterns with other tools (research/)

Keep this README updated as documentation structure evolves.
