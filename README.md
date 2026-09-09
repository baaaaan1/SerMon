<div align="center">

# 🖥️ Serial Monitor

*A modern, functional Windows serial-port monitor wrapped in an elegant dark **neumorphism (soft-UI)** skin.*

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-%E2%89%A56.5-46A2F1?logo=qt&logoColor=white)
![pyserial](https://img.shields.io/badge/pyserial-%E2%89%A53.5-166DFF?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)

</div>

---

## ✨ Features

- 🌗 **Neumorphism dark mode** — soft double-shadow painted in code, no image assets
- 📑 Native **menu bar** (`File` / `Connection` / `View` / `Help`) + neumorphic **top toolbar** and **bottom bar**
- 🧭 **Port + baud** selection and **Refresh ports**
- 🔌 **Connect / Disconnect**, plus a **DTR toggle**
- 🔁 **Auto-Reconnect** (retries every ~1 s when the link drops)
- 🧹 **Auto-Clear on Reconnect**
- 🖥️ Terminal with colour-coded **RX / TX / system** output and **auto-scroll**
- 🕑 **Timestamps** — optional `[HH:MM:SS.mmm]` prefix on RX/TX lines (`Ctrl+T`)
- 📋 **Copy terminal**, **Export to TXT**, **Clear**
- ⌨️ **TX input** — send with a button or <kbd>Enter</kbd>
- 📊 Live status: online/offline, RX/TX byte counters, DTR state, `port @ baud`
- 🔤 **Bundled UI font** — ships **Nunito Sans** (with **Nunito** fallback, SIL OFL) so the UI renders identically even on machines that don't have them


## 📥 Requirements

| Dependency | Version |
|------------|---------|
| Python     | 3.9+    |
| PySide6    | ≥ 6.5   |
| pyserial   | ≥ 3.5   |

## 🚀 Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 🏃 Usage

```powershell
python main.py
```

On the toolbar:

1. Pick a **port** (e.g. `COM9`) and a **baud rate**.
2. Press **Connect**.
3. Use the **DTR** button to toggle the DTR line.
4. Toggle **🕑 TimeSt** (or press <kbd>Ctrl+T</kbd>) to prefix each RX/TX line with a timestamp.
5. Type in the **TX input** and send with the **Send** button or <kbd>Enter</kbd>.

## ⌨️ Keyboard shortcuts

| Action               | Shortcut            |
|----------------------|---------------------|
| Connect / Disconnect | <kbd>Ctrl+Enter</kbd> |
| Refresh ports        | <kbd>F5</kbd>       |
| Timestamps           | <kbd>Ctrl+T</kbd>   |
| Export to TXT        | <kbd>Ctrl+E</kbd>   |
| Copy terminal        | <kbd>Ctrl+Shift+C</kbd> |
| Clear terminal       | <kbd>Ctrl+L</kbd>   |
| Quit                 | <kbd>Ctrl+Q</kbd>   |

## 🖼️ Screenshots

![Main window](assets/screenshot.png)

## 📁 Project layout

```
main.py          window, menu bar, toolbar, bottom bar and wiring
serial_engine.py Qt-core SerialManager (threaded reader + auto-reconnect)
widgets.py       painted neumorphism widgets (button / frame / terminal)
theme.py         palette, fonts, global QSS
```

## 📦 Build a Windows EXE (PyInstaller)

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name SerialMonitor --add-data "assets/fonts;assets/fonts" main.py
```

The executable is written to `dist\SerialMonitor.exe`.

## 📄 License

> Not yet set. Add a `LICENSE` file if you intend to share or publish this project.
