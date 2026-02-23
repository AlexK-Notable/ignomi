# Architecture Diagrams

Visual reference for the Ignomi launcher's architecture and workflows. Generated 2025-11-09.

## Diagram Index

| # | Diagram | Description |
|---|---------|-------------|
| 01 | [System Architecture](ignomi-01-system-architecture-2025-11-09T21-20-22-304Z.png) | Top-level view of IgnisApp and its managers (WindowManager, CssManager, ConfigManager, IconManager) |
| 02 | [Panel Structure](ignomi-02-panel-structure-2025-11-09T21-20-22-706Z.png) | UML class diagram of BookmarksPanel, SearchPanel, and FrequentPanel with attributes and methods |
| 03 | [Service Layer](ignomi-03-service-layer-2025-11-09T21-20-23-080Z.png) | How panels connect to ApplicationsService and FrecencyService, both extending GObject/BaseService |
| 04 | [App Lifecycle](ignomi-04-app-lifecycle-2025-11-09T21-20-23-504Z.png) | State machine for the Ignis application: Initialize, ConfigLoaded, Ready, Running, Reloading, Quit |
| 05 | [Frecency Dataflow](ignomi-05-frecency-dataflow-2025-11-09T21-20-23-868Z.png) | Sequence diagram showing app launch recording through FrecencyService to SQLite and back to UI |
| 06 | [Widget Hierarchy](ignomi-06-widget-hierarchy-2025-11-09T21-20-24-254Z.png) | Ignis widget inheritance tree: BaseWidget, Window, Entry, EventBox, Box, Button, Label |
| 07 | [Search Userflow](ignomi-07-search-userflow-2025-11-09T21-20-24-630Z.png) | User interaction flow: open panel, type query, filter apps, navigate with arrows, launch app, close |
| 08 | [Config Manager State](ignomi-08-config-manager-state-2025-11-09T21-20-25-037Z.png) | State machine for config loading: Uninitialized, Parsing, Error, Parsed, Ready, Reloading |
| 09 | [CSS Pipeline](ignomi-09-css-pipeline-2025-11-09T21-20-25-447Z.png) | Flow from CSS/SASS file through apply_css, priority levels, storage, and signal emission to widget styles |
| 10 | [Pinning System](ignomi-10-pinning-system-2025-11-09T21-20-25-838Z.png) | Sequence diagram for bookmark add/remove: user click, signal, bookmarks file I/O, panel refresh |

## How to Read These

- **Diagrams 01, 03, 06** are structural (class/component relationships)
- **Diagrams 04, 08** are state machines (application and config lifecycle)
- **Diagrams 05, 07, 10** are behavioral (sequence/flow diagrams showing runtime interactions)
- **Diagram 09** is a pipeline diagram (CSS loading process)
- **Diagram 02** is a UML class diagram specific to Ignomi's three panel classes

## Notes

These diagrams represent the Ignis framework architecture and Ignomi's design as of November 2025. Some details may refer to planned features (e.g., diagram 10 shows a "pin button" signal-based flow, while the current implementation uses right-click context menus and direct `refresh_from_disk()` calls).

For current implementation details, see the [launcher README](../../launcher/README.md).
