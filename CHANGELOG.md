# Changelog

This file records user-visible changes and Windows packaging notes. Published versions and downloads are listed on [GitHub Releases](https://github.com/baaaaan1/SerMon/releases).

## 1.3.0 (Unreleased)

### Added

- Per-user settings for the selected port/baud, DTR, reconnect and terminal toggles, line-ending mode, window geometry, and recent command history. Preferences restore without connecting automatically.
- Terminal-style command history with Up/Down navigation and draft restoration. Tab completion and Ctrl+Space suggestions use sent commands and received-text memory.
- A two-column Connection / Behavior panel, terminal-header Auto Scroll toggle, and reorganized command/action area.
- A Help menu with a themed, scrollable Keyboard Shortcuts dialog, additional action shortcuts, keyboard-focusable buttons, accessible names, and shortcut-aware tooltips.
- Offline Lucide icons, a bundled dropdown chevron, and the required ISC/MIT notices.

### Changed

- Command input is limited to 4,096 characters. History retains up to 200 entries, omits blank commands and consecutive duplicates, and is persisted as plain text; received-text suggestions remain memory-only.
- Clear Command History removes persisted commands and completion memory without changing the unsent draft. Clearing terminal output leaves command history intact.
- A missing saved port remains selected as unavailable instead of silently switching devices.
- Connection state distinguishes Connect, Disconnect, and Cancel Retry; port/baud controls are locked during active or pending connections.
- The main title bar and Keyboard Shortcuts dialog follow the main page background. The maximize control updates its tooltip and repaint state when switching to restore.

### Fixed

- Retry handling after initial open failures, dropped links, DTR failures, and read/write errors. Turning retries off preserves a live link or initial explicit open; turning them back on can resume an uncanceled failed request.
- Cancellation and rapid reconnect races: stale events and late-open handles cannot affect a newer connection, and shutdown interrupts retry waits cleanly.
- Auto Clear now runs on every successful connection, including automatic reconnects, before the connected status message is added.
- Failed or partial writes retain command input and do not add the command to history. Unmodified Enter sends exactly the typed input instead of accepting a completion; Ctrl+Enter controls the connection.
- Incoming output preserves selection and paused scroll position. Manual scrolling pauses Auto Scroll; reaching the bottom or enabling it resumes following and synchronizes the controls.
- CR, LF, and CRLF display normalization across serial chunks without changing the selected wire suffix or RX record delimiter. Exported UTF-8 text uses explicit LF newlines.
- Duplicate toggle signal handling and ordering between queued RX fragments and serial status changes.

### Windows Packaging

- Application metadata, Qt application version, native EXE File/Product Version fields, MSI version, and artifact names are aligned at 1.3.0.
- Builds produce `SerialMonitor-v1.3.0.exe` and `SerialMonitor-v1.3.0.msi` for Windows x64. The existing MSI upgrade identity is preserved.
- README installation/build guidance and the [Windows packaging checklist](installer/README.md) describe version maintenance, bundled resources, signing, and release publication.

### Validation

- All 83 regression tests passed, covering serial lifecycle, line endings, persistence, keyboard actions, command history/completion, and terminal widgets without serial hardware.
- The standalone EXE was checked for bundled modules, Qt's Windows platform plugin, fonts, icons, and notices, then launched and closed cleanly.
- MSI version, x64 architecture, and upgrade identity were checked. Extracted executable and license payloads matched their originals by SHA256.
- Validation builds are unsigned. A real-device session and a full MSI install/upgrade/uninstall cycle were not performed; these remain release checklist items.
