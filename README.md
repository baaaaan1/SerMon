<div align="center">

# 🖥️ Serial Monitor

*A modern, functional Windows serial-port monitor wrapped in an elegant dark **neumorphism (soft-UI)** skin.*

[![Release](https://img.shields.io/github/v/release/baaaaan1/SerMon?display_name=tag&sort=semver)](https://github.com/baaaaan1/SerMon/releases/latest)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-%E2%89%A56.5-46A2F1?logo=qt&logoColor=white)
![pyserial](https://img.shields.io/badge/pyserial-%E2%89%A53.5-166DFF?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## ✨ Features

- 🌗 **Neumorphism dark mode** — soft double shadows and controls painted in code
- 🪟 **Custom frameless title bar** — native dragging, Aero Snap, edge resizing, and minimize/maximize/close controls
- 🖼️ **Dedicated application icon** — displayed as the window/taskbar app icon without cluttering the custom title bar
- 📑 Native **menu bar** (`File` / `Connection` / `View` / `About`) with neumorphic **top toolbar** and **bottom bar**
- 🧭 **Port + baud** selection and **Refresh ports**
- 🔌 **Connect / Disconnect**, plus a **DTR toggle**
- 🔁 **Auto-Reconnect** (retries every ~1 second when the link drops)
- 🧹 **Auto-Clear on Reconnect**
- 🖥️ Terminal with colour-coded **RX / TX / system** output and **auto-scroll**
- 🕑 **Timestamps** — optional `[HH:MM:SS.mmm]` prefix on RX/TX lines (`Ctrl+T`)
- 📋 **Copy terminal**, **Export to TXT**, and **Clear** actions
- ⌨️ **TX input** — send with a button or <kbd>Enter</kbd>
- ↵ Shared **line-ending mode** for TX and RX parsing — No line ending, Newline, Carriage return, or Both NL & CR (default)
- 📊 Live status — online/offline, RX/TX byte counters, DTR state, and `port @ baud`
- 🔤 **Bundled UI font** — ships **Nunito Sans** with a **Nunito** fallback (SIL OFL) for consistent rendering

## 📥 Requirements

| Dependency | Version |
|------------|---------|
| Python     | 3.10+   |
| PySide6    | ≥ 6.5   |
| pyserial   | ≥ 3.5   |

## 🚀 Installation

```powershell
git clone https://github.com/baaaaan1/SerMon.git
cd SerMon
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 🏃 Usage

```powershell
python main.py
```

On the toolbar and bottom bar:

1. Pick a **port** (for example, `COM9`) and a **baud rate**.
2. Press **Connect**.
3. Use the **DTR** button to toggle the DTR line.
4. Toggle **TimeSt** (or press <kbd>Ctrl+T</kbd>) to prefix each RX/TX line with a timestamp.
5. Choose the shared **Line ending** mode. It appends the matching TX suffix and parses RX records across serial chunk boundaries.
6. Type in the **TX input** and send with the **Send** button or <kbd>Enter</kbd>.

### Line-ending modes

The footer selector controls both the bytes appended to transmitted text and the delimiter used to parse received records. RX parsing preserves partial UTF-8 characters and delimiters that arrive across separate serial chunks.

| Mode | TX suffix | RX delimiter |
|------|-----------|--------------|
| No line ending | None | Stream text immediately |
| Newline | `\n` | `\n` |
| Carriage return | `\r` | `\r` |
| Both NL & CR (default) | `\r\n` | Exact `\r\n` sequence |

## ⌨️ Keyboard shortcuts

| Action               | Shortcut               |
|----------------------|------------------------|
| Connect / Disconnect | <kbd>Ctrl+Enter</kbd>   |
| Refresh ports        | <kbd>F5</kbd>           |
| Timestamps           | <kbd>Ctrl+T</kbd>       |
| Export to TXT        | <kbd>Ctrl+E</kbd>       |
| Copy terminal        | <kbd>Ctrl+Shift+C</kbd> |
| Clear terminal       | <kbd>Ctrl+L</kbd>       |
| About                | <kbd>F1</kbd>           |
| Quit                 | <kbd>Ctrl+Q</kbd>       |

## 🖼️ Screenshot

![Serial Monitor main window](assets/screenshot.png)

## 📁 Project layout

```text
main.py          Main window, menus, toolbars, status display, and signal wiring
line_endings.py  Shared TX suffix definitions and incremental RX text parser
frameless.py     Custom title bar, window controls, native drag, and resize support
serial_engine.py Threaded serial manager and automatic reconnect handling
widgets.py       Painted neumorphism buttons, frames, and terminal widget
theme.py         Shared palette, bundled-font loader, and global Qt style sheet
about.py         Frameless neumorphic About panel (metadata, credits, and links)
assets/          Application icon, screenshot, and bundled Nunito fonts
requirements.txt Python runtime dependencies
tests/            Standard-library tests for line-ending and stream parsing
```

## 📦 Build a Windows EXE (PyInstaller)

Install the build dependencies and run PyInstaller from the project root:

```powershell
python -m pip install pyinstaller -r requirements.txt
$version = "1.2.0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "SerialMonitor-v$version" --icon "assets/app_icon.ico" --add-data "assets;assets" main.py
```

The executable is written to `dist\SerialMonitor-v1.2.0.exe`. The `--add-data` option is required so the bundled fonts and runtime application icon remain available in the packaged app.

To build the MSI, install WiX Toolset v3 and run:

```powershell
New-Item -ItemType Directory -Force -Path "build\installer"
& "C:\Program Files (x86)\WiX Toolset v3.14\bin\candle.exe" -arch x64 "-dVersion=$version" -o "build\installer\" "installer\SerialMonitor.wxs"
& "C:\Program Files (x86)\WiX Toolset v3.14\bin\light.exe" -ext WixUIExtension -o "dist\SerialMonitor-v$version.msi" "build\installer\SerialMonitor.wixobj"
```

## 🏷️ Releases

Stable versions and downloadable build artifacts are available on the [GitHub Releases](https://github.com/baaaaan1/SerMon/releases) page.

## 📄 License

Released under the **MIT License** — see [LICENSE](LICENSE) for the full text.

Copyright (c) 2026 baaaaan1

### 👀 Support My Work

If my projects have been useful to you, you can support my work through <strong><a href="https://tako.id/Baaaaan1">tako.id</a></strong>, a platform for sending tips to creators. Your support helps fund hardware prototypes, components, testing, and future open-source projects.

<p>
  <a href="https://tako.id/Baaaaan1"><img alt="Scan to visit tako.id/Baaaaan1" src="assets/qr-code.svg" width="160" height="160"></a>
</p>

<sub>Scan or click the QR code to support my work at <a href="https://tako.id/Baaaaan1">tako.id/Baaaaan1</a>.</sub>

</div>
