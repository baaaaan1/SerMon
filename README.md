# Serial Monitor

A desktop **serial port monitor / terminal** built with **Python**, **PySide6** (Qt for Python) and **pyserial**.

The application is structured so the serial communication layer is completely
decoupled from the GUI: the serial engine has **no PySide6 dependency**, and the
UI talks to it through a thin bridge that adapts engine callbacks to Qt signals.
This makes the communication core unit-testable, reusable from a CLI, and ready
for new protocol/parser extensions without touching the UI.

## Purpose

- Monitor raw data flowing in from a serial port (text or hex).
- Send data to the connected device.
- Show connection state and errors clearly.
- Provide an **extensible protocol layer** so future parsers/features can be
  added without rewriting the interface or the engine.

## Features (Foundation)

- Isolated virtual environment (`.venv`) with pinned runtime dependencies.
- Clean separation of concerns: `app` (UI) / `serial_engine` (engine) / `services`.
- Qt-free serial engine with a background reader thread.
- Application-wide logging (console + optional rotating file).
- JSON-based configuration with defaults merging.
- Protocol parser registry for future extensibility.
- Type hints and docstrings throughout.

## Setup

Requires **Python 3.10+** (developed on 3.14).

```powershell
# From the repository root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Run the application

```powershell
python src/main.py
```

Or, after an editable install:

```powershell
pip install -e .
serial-monitor
```

## Development

### Layout

```
src/
├── main.py            # entry point (bootstrap config + logging + QApplication)
├── app/               # PySide6 UI (Qt-only)
│   ├── application.py # QApplication setup + theme loading
│   ├── window.py      # MainWindow (wires widgets to the bridge)
│   ├── bridge.py      # ONLY Qt<->serial adapter (engine callbacks -> Qt signals)
│   ├── state.py       # shared UI state
│   ├── models/        # terminal / tx-input / quick-commands view models
│   ├── widgets/       # terminal, connection panel, counters, tx-input, activity…
│   ├── theme/         # runtime theme (palette + palette→QSS renderer + manager)
│   └── dialogs/       # modal dialogs
├── serial_engine/       # Qt-free serial engine (pyserial + stdlib only)
│   ├── config.py      # serial connection config + validation errors
│   ├── manager.py     # engine facade + observer API
│   ├── worker.py      # background reader thread
│   ├── session.py     # pyserial connection lifecycle
│   ├── port_scanner.py# port enumeration -> PortInfo
│   ├── exceptions.py  # exception hierarchy
│   └── protocols/     # parser extension point (ABC + registry)
│       ├── base.py    # ProtocolParser ABC + ParsedEvent
│       ├── hex.py     # HexParser
│       ├── line.py    # LineParser
│       └── registry.py# ProtocolRegistry + @register decorator
├── services/          # cross-cutting concerns
│   ├── config.py      # AppConfig/SerialConfig + JSON persistence
│   ├── logger.py      # logging configuration (console + optional rotating file)
│   ├── formatter.py   # byte/display formatting (hex/ASCII + timestamp)
│   ├── reconnect.py   # reconnect/backoff policy
│   └── errors.py      # error handling strategy
└── resources/
    └── icons/         # app icon (serial_monitor.ico)
```

### Architecture rules

- **`serial_engine/` must never import `PySide6`** (or any Qt module). It only uses
  `pyserial` and the standard library. The serial engine exposes plain
  callbacks, not Qt signals.
- **`app/` must never import `pyserial`.** Widgets talk only to the
  `SerialBridge` signals.
- Only `app/bridge.py` may know about both Qt and the serial engine.

> **Naming note:** the engine package is called `serial_engine` — not `serial` —
> because pyserial's importable package is also named `serial`. A `src/serial/`
> package would shadow pyserial and break `from serial.tools import list_ports`.
> `serial_engine` keeps the engine separate while avoiding that collision.

### Adding a new protocol parser

1. Subclass `serial_engine.protocols.base.ProtocolParser` and implement `feed()`.
2. Register it, e.g. with the `@register("name")` decorator or
   `registry.register("name", MyParser)`.
3. Select it by name — no UI changes required.

Built-in parsers (registered on the default `registry`):

- `line` — `LineParser`: buffers bytes and emits one `"line"` event per
  newline-delimited line (handles `\n` and `\r\n`).
- `hex` — `HexParser`: emits incoming bytes as an uppercase, space-separated
  hex string.

The parser selector in the UI is populated from `registry.names()`, so a new
parser becomes selectable automatically once registered.

### Tests

```powershell
python -m pytest
```

Tests live in `tests/` and cover configuration round-tripping, the protocol
registry, and port enumeration.

## Building an executable (EXE / MSI)

The app can be frozen into a standalone Windows program. An **MSI** is an
installer package; PyInstaller cannot produce an MSI directly, so you build an
EXE with PyInstaller and then wrap that build with **WiX Toolset**.

### Prerequisites

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install pyinstaller
```

> Run the build from a **normal (non-admin)** terminal: PyInstaller warns when
> run as Administrator and will refuse to build at all in version 7.

### Build a one-file EXE (from the existing spec)

The repository already ships a PyInstaller spec at the root (`SerialMonitor.spec`)
that produces a single, windowed executable with the app icon and the pyserial
Windows port-list plugin included:

```powershell
pyinstaller SerialMonitor.spec
```

Output: `dist\SerialMonitor.exe`.

Alternatively, the same result without the spec file:

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name SerialMonitor `
  --icon src\resources\icons\serial_monitor.ico `
  --add-data "src\resources;resources" `
  --hidden-import serial.tools.list_ports_windows `
  src\main.py
```

Notes:

- `--add-data "src\resources;resources"` — the separator is `;` on Windows
  (`:` on macOS/Linux). It bundles the `resources` folder into the exe.
- `--hidden-import serial.tools.list_ports_windows` — needed because pyserial's
  Windows port enumeration lives in a module that pyserial loads dynamically.
- `--onefile` unpacks to a temporary folder at launch, so the first start is a
  little slower; use `--onedir` instead to get a portable folder in
  `dist\SerialMonitor\` that starts faster.

### Build an MSI (WiX Toolset)

1. Create a **one-folder** build so the payload is a directory of files:

   ```powershell
   pyinstaller --noconfirm --clean --onedir --windowed --name SerialMonitor `
     --icon src\resources\icons\serial_monitor.ico `
     --add-data "src\resources;resources" `
     --hidden-import serial.tools.list_ports_windows `
     src\main.py
   ```

   This produces `dist\SerialMonitor\SerialMonitor.exe` plus the supporting
   DLLs / data files.

2. Author a `Product.wxs` (WiX) that installs everything under
   `dist\SerialMonitor\` and a start-menu shortcut. Example:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
     <Product Id="*"
              Name="Serial Monitor"
              Language="1033"
              Version="0.1.0"
              Manufacturer="Serial Monitor"
              UpgradeCode="PUT-A-GUID-HERE">
       <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" />
       <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
       <MediaTemplate EmbedCab="yes" />
       <Icon Id="AppIcon" SourceFile="src\resources\icons\serial_monitor.ico" />
       <Property Id="ARPPRODUCTICON" Value="AppIcon" />
       <Directory Id="TARGETDIR" Name="SourceDir">
         <Directory Id="ProgramFiles64Folder">
           <Directory Id="INSTALLFOLDER" Name="Serial Monitor">
             <Component Id="MainExe" Guid="*">
               <File Id="SerialMonitorExe"
                     Source="dist\SerialMonitor\SerialMonitor.exe"
                     KeyPath="yes" />
             </Component>
           </Directory>
         </Directory>
       </Directory>
       <Feature Id="Main" Title="Serial Monitor" Level="1">
         <ComponentRef Id="MainExe" />
       </Feature>
     </Product>
   </Wix>
   ```

   This is a minimal template: add a `<Component>` / `<File>` entry for **every**
   file in `dist\SerialMonitor\`, or use a harvesting tool (HeatWave, or WiX's
   `Files` element) to include the whole directory automatically.

3. Compile and link with WiX v3:

   ```powershell
   candle Product.wxs
   light -ext WixUtilExtension Product.wixobj -o dist\SerialMonitor.msi
   ```

   or, with WiX v4 / v5:

   ```powershell
   wix build Product.wxs -o dist\SerialMonitor.msi
   ```

### Alternative: Inno Setup (EXE installer)

If you prefer a self-extracting `.exe` installer instead of an MSI, use
**Inno Setup** (open-source) on the one-folder build above; it does not produce
an `.msi`.

### Python version compatibility

PyInstaller 6.x officially supports Python up to 3.13. The project currently
builds successfully on Python 3.14.4 with PyInstaller 6.22.2, but if a future
interpreter causes a freeze error, create a **Python 3.10–3.13** venv for
packaging only:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
pip install -r requirements.txt pyinstaller
pyinstaller SerialMonitor.spec
```

## Error handling strategy

- A single `SerialMonitorError` base class under `serial_engine.exceptions` with
  specific subclasses (`SerialConnectionError`, `SerialConfigError`,
  `SerialReadError`, `SerialWriteError`).
- All serial operations translate pyserial exceptions into these types.
- `services.errors.handle()` provides a consistent centralized entry point that
  always logs, can notify user-facing handlers, and can re-raise (optionally
  wrapped).
- UI surfaces `SerialConnectionError` and friends as status-bar messages and
  error signals rather than crashing.

## Roadmap

- [ ] **Phase 1 — Connection & live view (this foundation)**
  - [x] Project scaffold with isolated venv + dependencies
  - [x] Qt-free serial engine + background reader
  - [x] UI/serial bridge and main window
  - [x] Config, logging, error handling, protocol registry
- [ ] **Phase 2 — Protocol plugins**: line, hex, and streaming parsers wired to
  the UI; parser selection.
- [ ] **Phase 3 — Terminal UX**: send history, timestamp toggle, clear filters.
- [ ] **Phase 4 — Visualization**: byte/time plotting, packet stats.
- [ ] **Phase 5 — Automation**: scripting, auto-reconnect, connection profiles.
- [x] **Phase 6 (Windows only) — Packaging**: PyInstaller spec + `.exe` build;
  WiX `.msi` instructions documented. (macOS/Linux installers + CI still pending.)
