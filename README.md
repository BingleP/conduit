# Conduit

A desktop application for scanning your video library, identifying files that would benefit from re-encoding, and re-encoding them using hardware-accelerated ffmpeg — all from a clean, local web-based UI.

---

## What it does

- **Scans** media folders and extracts technical metadata from every video file using `ffprobe`
- **Watches** folders for changes — new or removed files are detected automatically without a manual rescan
- **Flags** files that need optimization based on configurable rules (high bitrate, H.264 Hi10P, AV1)
- **Encodes** flagged files using hardware-accelerated (or software) ffmpeg, with configurable codec, quality, container, resolution, audio, and video filter options
- **Remuxes** files into MKV without re-encoding when appropriate (e.g. HDR content)
- **Filters** audio and subtitle tracks by language, re-encodes lossy audio to Opus/AAC, copies lossless tracks
- **Custom Encode** — queue any selection of files with per-batch overrides and a custom output directory
- **Presets** — save and reuse custom encode configurations; six built-in presets included
- **Drag-and-drop** — drop files or folders onto the window; choose Custom Encode or Optimize from a popup

Runs as a desktop app (native window via pywebview) with an optional Web UI for network access.

---

## Requirements

### All platforms
- Python 3.10+
- ffmpeg and ffprobe

### Linux
- Arch, Debian/Ubuntu, Fedora, or openSUSE (other distros may work)
- Qt6 WebEngine system packages (installed automatically by `install.sh`)
- Optional portable release: AppImage

### macOS
- Unsigned DMG release artifact available for Apple Silicon / Intel runners as published by GitHub Actions
- ffmpeg and ffprobe available in PATH, or configure their paths in Conduit after first launch
- Because the DMG is unsigned, macOS will warn before opening it

### Windows
- Windows 11 (Windows 10 may work but is untested)
- Microsoft Edge WebView2 Runtime — pre-installed on all Windows 11 machines

### Hardware encoders (all platforms)
- **NVIDIA** — GTX 900 series or newer (NVENC)
- **Intel** — 6th gen Core or newer (Quick Sync)
- **AMD** — RX 400 series or newer (AMF)
- **VA-API** — any GPU via `/dev/dri` (Linux only)
- **Software (CPU)** — no GPU required; uses libx265 / libsvtav1 / libx264 / libvpx-vp9

---

## Installation

### Release artifacts

GitHub releases now target:
- Windows: `conduit-<version>-setup.exe`
- Linux: `Conduit-<version>-x86_64.AppImage`
- macOS: `Conduit-<version>-macos.dmg` (unsigned)
- Source: `conduit-<version>-source.zip`

### Linux

**1. Install ffmpeg**

```bash
# Arch / CachyOS
sudo pacman -S ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg

# Fedora
sudo dnf install ffmpeg

# openSUSE
sudo zypper install ffmpeg
```

**2. Clone and run the installer**

```bash
git clone https://github.com/BingleP/conduit.git
cd conduit
chmod +x install.sh && ./install.sh
```

The install script will:
1. Verify Python 3.10+ is available
2. Install the Qt6 WebEngine system package for your distro
3. Create an isolated Python virtual environment in `conduit/venv/`
4. Install all Python dependencies into the venv
5. Install application icons to `~/.local/share/icons/`
6. Install a `conduit` launcher to `~/.local/bin/`
7. Install a desktop entry so Conduit appears in your app menu

No system Python is modified. Everything outside of the Qt system package lives in your home directory.

**3. Launch**

Search for **Conduit** in your app menu, or run:

```bash
conduit
```

---

### Windows

**1. Install Python 3.10+**

Download from [python.org](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"**.

**2. Install ffmpeg**

Download a Windows build from [ffmpeg.org](https://ffmpeg.org/download.html) (the [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) full build is recommended). Extract it and add the `bin` folder to your system PATH.

To verify: open a terminal and run `ffmpeg -version`.

**3. Clone or download the repo**

```
git clone https://github.com/BingleP/conduit.git
cd conduit
```

Or download and extract the ZIP from GitHub.

**4. Run the installer**

Open PowerShell in the conduit directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

The install script will:
1. Verify Python 3.10+ is available
2. Create an isolated Python virtual environment in `conduit\venv\`
3. Install all Python dependencies into the venv
4. Create `conduit.bat` — a no-console launcher in the conduit directory
5. Create a **Start Menu** shortcut with the Conduit icon

**5. Launch**

Search for **Conduit** in the Start Menu, or double-click `conduit.bat`.

---

## Usage

### Desktop app (Linux)

```bash
conduit
```

### Desktop app (Windows)

Double-click `conduit.bat` or launch from the Start Menu.

The app opens a native window. All services (server, encoder, scanner) run only while the window is open and stop when you close it.

### Running tests
After installation, run the automated test suite from the project root:

```bash
./venv/bin/python -m pytest
```

The pytest configuration also enables coverage output automatically and writes `coverage.xml` for CI.

If you are not using the bundled virtual environment, install `requirements.txt` first and then run:

```bash
python -m pytest
```

### Headless / server mode
Run Conduit without a window, exposing the Web UI on your network:

**Linux:**
```bash
conduit --no-gui
```

**Windows:**
```
conduit.bat --no-gui
```

The server starts on `127.0.0.1:8000` by default. To allow access from other devices, enable the Web UI in **Settings → Network** and restart.

**Linux — stop headless mode:**
```bash
pkill -f desktop.py
```

### Running as a systemd user service (Linux only)

If you want Conduit to run automatically in the background when you log in:

**1. Enable the Web UI**

Open Conduit, go to **Settings → Network**, enable Web UI, set your desired port, and save. Then close the app.

**2. Create the service file**

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/conduit.service <<EOF
[Unit]
Description=Conduit media server
After=network.target

[Service]
Type=simple
ExecStart=$HOME/.local/bin/conduit --no-gui
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

**3. Enable and start it**

```bash
systemctl --user daemon-reload
systemctl --user enable conduit   # start on login
systemctl --user start conduit    # start now
```

**4. Useful commands**

```bash
systemctl --user status conduit   # check status
systemctl --user stop conduit     # stop
systemctl --user disable conduit  # remove from autostart
journalctl --user -u conduit -f   # follow logs
```

The service runs only when your user session is active. It is not a system-wide daemon.

---

## Settings

All settings are accessible from the gear icon in the top-right corner. They are saved to `config.json` in the Conduit directory. The settings panel uses a scrollable left sidebar to navigate between tabs.

A **Load preset** bar sits at the top of the settings panel at all times. Selecting a preset from the dropdown immediately fills all encode fields with that preset's values — review and click **Save** to apply them as your global defaults.

### Encoder

| Setting | Description | Default |
|---|---|---|
| Hardware Accelerator | GPU/CPU backend: NVENC (NVIDIA), QSV (Intel), AMF (AMD), VA-API, or Software (CPU) | `nvenc` |
| VA-API Device Path | Render node path for VA-API encoding (e.g. `/dev/dri/renderD128`). **Linux only.** | `/dev/dri/renderD128` |
| ffmpeg Path | Path to ffmpeg binary | `ffmpeg` |
| ffprobe Path | Path to ffprobe binary | `ffprobe` |
| Extra ffmpeg Arguments | Additional arguments appended to every ffmpeg encode command before the output path. Supports quoted arguments. Not applied to remux jobs. | _(empty)_ |

### Video

| Setting | Description | Default |
|---|---|---|
| Output Codec | Target codec: HEVC, AV1, H.264, or VP9 | `hevc` |
| Quality (CQ/QP) | Encode quality (0–51). Lower = better quality, larger file | `24` |
| Output Container | Container format: MKV, MP4, or WebM | `mkv` |
| Scale Height | Downscale to this height (e.g. 1080, 720). Aspect ratio preserved. Only downscales — no upscaling. | _(off)_ |
| Pixel Format | Force a pixel format: `auto` (match source), `yuv420p` (8-bit), `yuv420p10le` (10-bit). Not applied to VA-API. | `auto` |
| Encoder Speed | Speed/compression trade-off: Fast, Medium, Slow, Very Slow | `medium` |
| Frame Rate Cap | Limit output frame rate (60, 30, or 24 fps). Not applied to remux jobs. | _(off)_ |
| Deinterlace | Apply `yadif` deinterlace filter for interlaced sources (e.g. DVD rips, old TV captures). Not applied to remux jobs. | `off` |
| Auto-Crop Black Bars | Run a `cropdetect` pre-pass to detect and crop letterboxing/pillarboxing. Not applied to remux jobs. | `off` |
| Denoise | Apply `hqdn3d` spatial/temporal denoising filter. Useful for noisy sources (VHS rips, compressed web video). Not applied to remux jobs. | `off` |

**Codec/container compatibility** is enforced live — incompatible combinations are automatically disabled:
- VP9 is not compatible with MP4 (selecting VP9 auto-switches container to WebM)
- H.264 and HEVC are not compatible with WebM (selecting either auto-switches container to MKV)
- WebM requires Opus audio (AAC and Copy are disabled)
- MP4 does not support Opus audio (Opus is disabled; auto-switches to AAC)

**VP9 hardware encoding** is supported on Intel QSV (Ice Lake / 10th gen+) and VA-API. NVENC and AMF do not have VP9 encoders — selecting VP9 with those accelerators falls back to software `libvpx-vp9`.

### Audio

| Setting | Description | Default |
|---|---|---|
| Lossy Track Handling | What to do with lossy audio tracks: encode to Opus, encode to AAC, or copy | `opus` |
| Keep Audio Languages | Language tracks to include. Empty = keep all. | `eng`, `jpn` |
| Force Stereo Downmix | Downmix all re-encoded audio tracks to stereo (2.0) | `off` |
| Loudness Normalization | Apply EBU R128 normalization (−23 LUFS, −2 dBTP true peak) to re-encoded tracks | `off` |
| Force Encode Audio | Re-encode audio even if the source track is lossless (FLAC, TrueHD, DTS-HD MA). By default, lossless tracks are always copied to preserve quality. | `off` |

If no matching language track is found, the first audio track is kept as a fallback.

### Subtitles

| Setting | Description | Default |
|---|---|---|
| Subtitle Mode | `copy` — pass subtitle tracks through unchanged. `strip` — remove all subtitle tracks. Only MKV preserves subtitles; MP4 and WebM strip them regardless. | `copy` |

### Flagging

| Setting | Description | Default |
|---|---|---|
| High Bitrate Threshold | Files above this bitrate (kbps) are flagged | `25000` (25 Mbps) |
| Flag AV1 files | Flag AV1 files for re-encoding | `true` |

Files are flagged for optimization if any of the following are true:
- **Hi10P** — H.264 with 10-bit color (poor hardware decode support)
- **AV1** — AV1 codec (when AV1 flagging is enabled)
- **High Bitrate** — bitrate exceeds the configured threshold

Click the flag icon on any file to see exactly why it was flagged.

### Network

| Setting | Description | Default |
|---|---|---|
| Enable Web UI | Allow network access to the interface | `false` |
| Bind Address | IP to listen on (`0.0.0.0` = all interfaces) | `0.0.0.0` |
| Web UI Port | Port for network clients | `8000` |

Network changes require a restart to take effect.

---

## Folder Monitoring

Conduit automatically watches every added folder for file changes using OS-native filesystem events (inotify on Linux).

**While the app is open**, any video file added, removed, or renamed triggers an incremental re-scan. A short debounce period (3 seconds) lets file copies and batch moves settle before the scan runs.

**When the app is reopened**, every folder is immediately queued for an incremental scan. Only files whose modification time has changed since the last scan are re-probed — unchanged files are skipped, so startup scans on large libraries are fast.

**Scan queue**: scans run one folder at a time. If multiple folders trigger re-scans simultaneously, they queue up and run sequentially. The scan indicator in the top bar shows current progress and how many scans are waiting.

---

## Presets

The **Presets** tab (Settings) lets you save and reuse full encode configurations. When you open the **Encode** modal, selecting a preset from the dropdown fills all override fields at once. You can also load any preset directly in the Settings panel using the **Load preset** bar to use it as your global default.

Each preset stores all 16 encode fields: hardware accelerator, codec, quality, container, scale height, pixel format, encoder speed, subtitle mode, audio action, force stereo, loudness normalization, force encode audio, frame rate cap, deinterlace, auto-crop, denoise, and extra ffmpeg arguments.

### Built-in presets

Built-in presets are read-only but each has an **Accelerator** selector in the Presets tab so you can choose the GPU backend that matches your hardware. The selection is saved to your config and applied whenever the preset is used.

| Preset | Codec | Audio | Container | Notes |
|---|---|---|---|---|
| **Default** | HEVC | Opus | MKV | Solid all-round preset. Good starting point for most libraries. |
| **Archive Quality** | HEVC | Copy | MKV | Software x265 at CQ 18. Near-lossless quality for permanent storage. Large files. |
| **Plex / Jellyfin** | H.264 | AAC | MP4 | Broad device compatibility. Direct plays on almost everything. |
| **Discord / Web** | H.264 | AAC | MP4 | Compact H.264 for sharing. CQ 28 keeps files small. |
| **AV1 Efficient** | AV1 | Opus | MKV | Hardware AV1. Requires RTX 4000+ (NVENC), Intel Arc/12th gen+ (QSV), or RX 7000+ (AMF). |
| **Tower Unite** | VP9 | Opus | WebM | Required for synced playback in Tower Unite condos without CEFCodecFix. Always software-encoded. |

---

## Encode

The **Encode** button opens a per-batch encode modal. Any selected files can be queued with settings that override the global defaults for that batch only.

### Per-batch overrides

All 16 encode fields are available as per-batch overrides — the same fields available in Settings and the Preset editor. Selecting a preset from the dropdown at the top of the modal fills all fields at once.

Impossible codec/container/audio combinations are disabled live as you change selections, with the same rules as the Settings panel.

### Encode error popup

If an encode fails, a popup shows the filename and the ffmpeg error output. If Extra ffmpeg Arguments were active at the time, the popup notes this so you know they may be the cause.

### Output location

By default, encoded files are saved next to their source files. You can choose a different output directory using the **Browse** button.

When an output directory is set:
- The output filename is `{original_stem}{ext}` written into the chosen directory
- The original file is always kept — it is never deleted or replaced
- The keep/replace original option is hidden (not applicable)

### Collision warning

If multiple selected files share the same filename stem and would write to the same output directory, Conduit warns you before encoding starts. You can go back to change the selection or output directory, or encode anyway.

### HDR handling

When the selection contains HDR files (HDR10+, Dolby Vision), a prompt appears asking whether to remux or re-encode them. Non-HDR files in the same batch are always encoded without prompting.

---

## Drag-and-Drop

Drag any video files or folders from your file manager and drop them onto the Conduit window.

A popup appears asking what to do with the dropped files:

- **Custom Encode** — opens the encode modal so you can choose settings for this batch before queuing
- **Optimize** — queues the files immediately using your global settings, same as the Optimize button

Dropped files that are not yet in your library are probed automatically and added to the queue. Files that are already tracked by Conduit are reused as-is.

Dropping a folder expands to all video files within it (including subdirectories).

---

## HDR content

When you queue HDR files for optimization, Conduit prompts you to choose:

- **Remux** — rewraps the file into MKV without re-encoding. Preserves full HDR metadata. No quality loss.
- **Re-encode** — re-encodes with your configured settings. HDR metadata may be reduced to HDR10.

For HDR content, remux is recommended unless file size reduction is the priority.

---

## Database

The **Database** tab (Settings) shows all files that Conduit has previously encoded or remuxed. From here you can re-flag individual files (or all at once) so they appear again in the optimization queue.

Useful if you want to re-encode files after changing your quality settings or switching to a different codec.

---

## Uninstall

### Linux

```bash
# Remove launcher, desktop entry, and icons
rm -f ~/.local/bin/conduit
rm -f ~/.local/share/applications/conduit.desktop
rm -rf ~/.local/share/icons/hicolor/*/apps/conduit.png
rm -f ~/.local/share/icons/hicolor/scalable/apps/conduit.svg

# Remove the app directory (includes venv and database)
rm -rf /path/to/conduit

# If you set up the systemd service
systemctl --user disable --now conduit
rm -f ~/.config/systemd/user/conduit.service
systemctl --user daemon-reload
```

### Windows

1. Delete the conduit folder
2. Remove the Start Menu shortcut from `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Conduit.lnk`

---

## Supported platforms

| Platform | Status |
|---|---|
| CachyOS / Arch Linux | Tested |
| Debian / Ubuntu | Supported via install script |
| Fedora | Supported via install script |
| openSUSE | Supported via install script |
| Other Linux distros | Should work — may need Qt6 WebEngine installed manually |
| Windows 11 | Supported |
| Windows 10 | Untested |
| macOS | Not supported |
