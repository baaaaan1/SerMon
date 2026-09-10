<div align="center">

# 🖥️ Serial Monitor

*A modern, functional Windows serial-port monitor wrapped in an elegant dark **neumorphism (soft-UI)** skin.*

[![Release](https://img.shields.io/github/v/release/baaaaan1/SerMon?display_name=tag&sort=semver)](https://github.com/baaaaan1/SerMon/releases/latest)
![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-%E2%89%A56.5-46A2F1?logo=qt&logoColor=white)
![pyserial](https://img.shields.io/badge/pyserial-%E2%89%A53.5-166DFF?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)

</div>

---

## ✨ Features

- 🌗 **Neumorphism dark mode** — soft double shadows and controls painted in code
- 🪟 **Custom frameless title bar** — native dragging, Aero Snap, edge resizing, and minimize/maximize/close controls
- 🖼️ **Dedicated application icon** — displayed as the window/taskbar app icon without cluttering the custom title bar
- 📑 Native **menu bar** (`File` / `Connection` / `View` / `Help`) with neumorphic **top toolbar** and **bottom bar**
- 🧭 **Port + baud** selection and **Refresh ports**
- 🔌 **Connect / Disconnect**, plus a **DTR toggle**
- 🔁 **Auto-Reconnect** (retries every ~1 second when the link drops)
- 🧹 **Auto-Clear on Reconnect**
- 🖥️ Terminal with colour-coded **RX / TX / system** output and **auto-scroll**
- 🕑 **Timestamps** — optional `[HH:MM:SS.mmm]` prefix on RX/TX lines (`Ctrl+T`)
- 📋 **Copy terminal**, **Export to TXT**, and **Clear** actions
- ⌨️ **TX input** — send with a button or <kbd>Enter</kbd>
- 📊 Live status — online/offline, RX/TX byte counters, DTR state, and `port @ baud`
- 🔤 **Bundled UI font** — ships **Nunito Sans** with a **Nunito** fallback (SIL OFL) for consistent rendering

## 📥 Requirements

| Dependency | Version |
|------------|---------|
| Python     | 3.9+    |
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

On the toolbar:

1. Pick a **port** (for example, `COM9`) and a **baud rate**.
2. Press **Connect**.
3. Use the **DTR** button to toggle the DTR line.
4. Toggle **TimeSt** (or press <kbd>Ctrl+T</kbd>) to prefix each RX/TX line with a timestamp.
5. Type in the **TX input** and send with the **Send** button or <kbd>Enter</kbd>.

## ⌨️ Keyboard shortcuts

| Action               | Shortcut               |
|----------------------|------------------------|
| Connect / Disconnect | <kbd>Ctrl+Enter</kbd>   |
| Refresh ports        | <kbd>F5</kbd>           |
| Timestamps           | <kbd>Ctrl+T</kbd>       |
| Export to TXT        | <kbd>Ctrl+E</kbd>       |
| Copy terminal        | <kbd>Ctrl+Shift+C</kbd> |
| Clear terminal       | <kbd>Ctrl+L</kbd>       |
| Quit                 | <kbd>Ctrl+Q</kbd>       |

## 🖼️ Screenshot

![Serial Monitor main window](assets/screenshot.png)

## 📁 Project layout

```text
main.py          Main window, menus, toolbars, status display, and signal wiring
frameless.py     Custom title bar, window controls, native drag, and resize support
serial_engine.py Threaded serial manager and automatic reconnect handling
widgets.py       Painted neumorphism buttons, frames, and terminal widget
theme.py         Shared palette, bundled-font loader, and global Qt style sheet
assets/          Application icon, screenshot, and bundled Nunito fonts
requirements.txt Python runtime dependencies
```

## 📦 Build a Windows EXE (PyInstaller)

Install the build dependency and run PyInstaller from the project root:

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name SerialMonitor --icon "assets/app_icon.ico" --add-data "assets;assets" main.py
```

The executable is written to `dist\SerialMonitor.exe`. The `--add-data` option is required so the bundled fonts and runtime application icon remain available in the packaged app.

## 🏷️ Releases

Stable versions and downloadable build artifacts are available on the [GitHub Releases](https://github.com/baaaaan1/SerMon/releases) page.

## 📄 License

> A project license has not been set yet. Add a `LICENSE` file before redistributing or publishing derivative builds.
