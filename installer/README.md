# Windows Packaging

Run builds from the repository root. The [main README](../README.md) contains the EXE and MSI commands; this guide covers version maintenance and distribution checks.

## Inputs and Outputs

| Input | Purpose |
|-------|---------|
| `about.py` | Application version shown in About and registered with Qt |
| `installer/version_info.txt` | PyInstaller Windows File/Product Version resource |
| `installer/SerialMonitor.wxs` | WiX v3 MSI definition, shortcuts, branding, and upgrade rules |
| `installer/license.rtf` | MIT license displayed by the installer |
| `assets/` | Runtime fonts, application/UI icons, and third-party notices |
| `LICENSE` | Project license installed as `LICENSE.txt` |

The current version is **1.3.0**. Build using a 64-bit Python environment, PyInstaller, and WiX Toolset v3.14. The tested build environment used Python 3.14.4, PySide6 6.11.2, PyInstaller 6.22.2, and WiX 3.14.1.

| Output | Use |
|--------|-----|
| `dist/SerialMonitor-v1.3.0.exe` | Standalone, windowed Windows x64 application |
| `dist/SerialMonitor-v1.3.0.msi` | Per-machine Windows x64 installer containing the same EXE |
| `build/installer/SerialMonitor-v1.3.0.wixobj` | Intermediate WiX object; not a download artifact |
| `dist/SerialMonitor-v1.3.0.wixpdb` | WiX debugging symbols; not required by end users |

`--add-data "assets;assets"` is required for runtime fonts, the application icon, dropdown SVG, and third-party notices. Menu/button SVG geometry is bundled in `icons.py`; there is no runtime Iconify dependency. `--version-file "installer/version_info.txt"` embeds the native version resource.

## Version Maintenance

1. Update `APP_VERSION` in `about.py` using a numeric `major.minor.patch` version accepted by Windows Installer.
2. Update `filevers`, `prodvers`, the FileVersion/ProductVersion strings, and OriginalFilename in `installer/version_info.txt`. Native numeric versions use four components; 1.3.0 is stored as `(1, 3, 0, 0)`.
3. Update versioned examples in the README, this guide, and the WiX header, and add the corresponding changelog entry. The documented build commands derive `$version` from `about.APP_VERSION` and pass it to WiX with `-dVersion`.
4. Rebuild the EXE before linking the MSI. WiX reads `dist/SerialMonitor-v$version.exe`, so an older or mismatched executable must not be reused.
5. Keep UpgradeCode `{971BC7E6-53FE-449C-B943-EAC1D50D12BC}` unchanged. It identifies the product family for upgrades; WiX generates a new ProductCode/PackageCode for each build.

The MSI installs in `%ProgramFiles%\Serial Monitor`, creates Start Menu and desktop shortcuts, upgrades older MSI versions, and blocks downgrades. It requires administrator approval. Both distribution forms use `%APPDATA%\SerMon\SerialMonitor.ini`; the MSI does not manage or remove that per-user file, which includes plain-text command history.

## Release Checklist

1. Run `.venv\Scripts\python.exe -m unittest discover -s tests -v` and inspect `git diff --check`.
2. Build the EXE and confirm its Windows FileVersion/ProductVersion and About dialog match `APP_VERSION`. Inspect PyInstaller warnings and verify the Windows Qt plugin, fonts, icons, and notices are present.
3. Launch the packaged application, confirm its main window responds, and close it normally. Test a real serial device, including reconnect, DTR, sending, RX parsing, saved settings, and command history.
4. If signing the application, sign and verify the EXE before building the MSI so the installer embeds that exact signed binary. Certificate/private-key material must stay outside the repository.
5. Compile/link the MSI with WiX and check ProductVersion, x64 architecture, the fixed UpgradeCode, shortcuts, and payloads. An extracted `SerialMonitorExe` must have the same SHA256 as the standalone EXE; the installed license must match `LICENSE`.
6. In a disposable Windows VM, test a fresh install, upgrade from the previous MSI, downgrade rejection, shortcut launch, and uninstall. Verify the intended per-user settings behavior separately.
7. If signing the installer, sign and verify the final MSI. Generate final SHA256 hashes only after all signing steps, because signing changes artifact bytes.
8. Review the source/docs diff, keep generated build artifacts out of Git, and publish the validated EXE/MSI with release notes and checksums as GitHub Release assets when the release is ready. A branch push or pull request does not upload those artifacts.

Example metadata and checksum inspection from the repository root:

```powershell
$version = python -c "from about import APP_VERSION; print(APP_VERSION)"
(Get-Item "dist\SerialMonitor-v$version.exe").VersionInfo | Format-List FileVersion,ProductVersion,OriginalFilename
Get-FileHash -Algorithm SHA256 "dist\SerialMonitor-v$version.exe", "dist\SerialMonitor-v$version.msi"
Get-AuthenticodeSignature "dist\SerialMonitor-v$version.exe", "dist\SerialMonitor-v$version.msi" | Format-List Path,Status
```

## v1.3.0 Validation Status

- All 83 regression tests passed without serial hardware.
- PyInstaller produced an x64 GUI EXE containing the expected application modules, Qt Windows plugin, runtime assets, and notices. Startup, responsiveness, and clean shutdown were verified.
- WiX produced an x64 MSI with ProductVersion 1.3.0 and the existing UpgradeCode. Extracted EXE and license payloads matched the originals by SHA256.
- Both validation artifacts are unsigned, so Windows may warn about an unknown publisher or SmartScreen reputation.
- No real-device test or system install/upgrade/uninstall cycle was performed. Payload extraction and metadata inspection do not replace those checks.

Generated `build/`, `dist/`, and `.spec` files are ignored intentionally. Do not force-add them to a source commit.
