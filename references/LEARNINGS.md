# Learnings

Reference-routed lessons, appended by self-learn (newest last). Each
entry carries its record id for provenance; regenerate nothing here —
this file is append-only.

## 2026-08-25 — lrn-95a39182

**Fact:** Ignis's `SystemdService.units` property performs a `LoadUnit` D-Bus round-trip per unit rather than returning a cached bulk list — iterating it against a full unit list (1000+ units on this host) would visibly freeze the UI thread. Use a curated/known unit list and resolve each unit lazily via `get_unit(name)` instead of enumerating `.units`.
