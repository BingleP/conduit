# Conduit

A desktop application for scanning your video library, identifying files that would benefit from re-encoding, and re-encoding them using hardware-accelerated ffmpeg — all from a clean, local web-based UI.

---

## What it does

- **Scans** media folders and extracts technical metadata from every video file using `ffprobe`
- **Watches** folders for changes — new or removed files are detected automatically without a manual rescan
- **Flags** files that need optimization based on configurable rules (high bitrate, H.264 Hi10P, AV1)
- **Encodes** flagged files using hardware-accelerated (or software) ffmpeg, with configurable codec, quality, container, resolution, and audio options
- **Remuxes** files into MKV without re-encoding when appropriate (e.g. HDR content)
- **Filters** audio and subtitle tracks by language, re-encodes lossy audio to Opus/AAC, copies lossless tracks
- **Custom Encode** — queue any selection of files with per-batch overrides and a custom output directory
- **Presets** — save and reuse custom encode configurations; includes a built-in Tower Unite preset

Runs as a desktop app (native window via pywebview) with an optional Web UI for network access.

---

## Requirements

- Linux (Arch, Debian/Ubuntu, Fedora, openSUSE)
- Python 3.10+
- ffmpeg and ffprobe
- watchdog (installed automatically — enables live folder monitoring)
- A supported GPU **or** CPU for encoding:
  - **NVIDIA** — GTX 900 series or newer (NVENC)
  - **Intel** — 6th gen Core or newer (Quick Sync)
  - **AMD** — RX 400 series or newer (AMF)
  - **VA-API** — any GPU with VA-API support (no vendor-specific drivers required)
  - **Software (CPU)** — no GPU needed; uses libx265 / libsvtav1 / libx264 / libvpx-vp9

---

## Installation

```bash
git clone https://github.com/BingleP/conduit.git
cd conduit
chmod +x install.sh && ./install.sh
```

The install script will:
1. Verify Python 3.10+ is available
2. Install the system webview dependency for your distro (webkit2gtk or Qt)
3. Create an isolated Python virtual environment in `conduit/venv/`
4. Install all Python dependencies into the venv
5. Install a `conduit` launcher to `~/.local/bin/`
6. Install a desktop entry so Conduit appears in your app menu

No system Python is modified. Everything outside of the webview system package lives in your home directory.

### Installing ffmpeg

Conduit requires `ffmpeg` and `ffprobe`. If they are not already installed:

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

---

## Usage

### Desktop app

Launch from your app menu by searching for **Conduit**, or run:

```bash
conduit
```

The app opens a native window. All services (server, encoder, scanner) run only while the window is open and stop when you close it.

### Headless mode

Run Conduit without a window, exposing the Web UI on your network:

```bash
conduit --no-gui
```

The server starts on `127.0.0.1:8000` by default. To access it from other devices, enable the Web UI in **Settings → Network** and restart.

Stop headless mode with `Ctrl+C`, or if running in the background:

```bash
pkill -f desktop.py
```

### Running as a systemd user service (optional)

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

All settings are accessible from the gear icon in the top-right corner of the app. They are saved to `config.json` in the Conduit directory.

### Encoder

| Setting | Description | Default |
|---|---|---|
| Hardware Accelerator | GPU/CPU backend: `nvenc` (NVIDIA), `qsv` (Intel), `amf` (AMD), `vaapi` (VA-API), `software` (CPU) | `nvenc` |
| ffmpeg Path | Path to ffmpeg binary | `ffmpeg` |
| ffprobe Path | Path to ffprobe binary | `ffprobe` |

### Video

| Setting | Description | Default |
|---|---|---|
| Output Codec | Target codec: HEVC, AV1, H.264, or VP9 | `hevc` |
| Quality (CQ/QP) | Encode quality. Lower = better quality, larger file | `24` |
| Output Container | Container format for encoded files: MKV, MP4, or WebM | `mkv` |
| Scale Height | Downscale video to this height (e.g. 1080, 720). Aspect ratio is preserved. `Auto` leaves resolution unchanged | `auto` |
| Pixel Format | Force a specific pixel format (e.g. `yuv420p` for maximum compatibility). `Auto` preserves the source pixel format | `auto` |
| Encoder Speed | Speed/quality trade-off preset (slow → fast). Faster presets encode quicker at the cost of slightly larger files | `medium` |
| Subtitle Mode | How to handle subtitle tracks: `copy` (pass through unchanged) or `strip` (remove all subtitles) | `copy` |

**VP9 hardware encoding** is supported on Intel QSV (`vp9_qsv`, requires Ice Lake / 10th gen or newer) and VA-API (`vp9_vaapi`). NVIDIA NVENC and AMD AMF do not have VP9 encoders — selecting VP9 with those accelerators silently falls back to software `libvpx-vp9`.

**WebM container** only supports VP9 and AV1 video. H.264 and HEVC are not compatible with WebM — use MKV instead.

**MP4 container** forces AAC audio (Opus is not reliably supported in MP4) and strips subtitle and attachment tracks.

### Audio

| Setting | Description | Default |
|---|---|---|
| Lossy Track Handling | What to do with lossy audio: re-encode to Opus, AAC, or copy | `opus` |
| Keep Audio Languages | Which language tracks to include in the output | `eng`, `jpn` |
| Force Stereo Downmix | Downmix all audio tracks to stereo (2.0) | `off` |
| Loudness Normalization | Apply EBU R128 loudness normalization (−23 LUFS, true peak −2 dBTP) | `off` |

Lossless tracks (TrueHD, DTS-HD MA, FLAC, PCM) are always copied regardless of the lossy handling setting. If no matching language track is found, the first audio track is kept as a fallback.

### Flagging

| Setting | Description | Default |
|---|---|---|
| High Bitrate Threshold | Files above this bitrate (kbps) are flagged | `25000` (25 Mbps) |
| Flag AV1 files | Flag AV1 files for re-encoding | `true` |

Files are flagged for optimization if any of the following are true:
- **Hi10P** — H.264 with 10-bit color (poor hardware decode support)
- **AV1** — AV1 codec (when AV1 flagging is enabled)
- **High Bitrate** — Bitrate exceeds the configured threshold

Click the flag icon on any file in the table to see exactly why it was flagged.

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

**While the app is open**, any video file added, removed, or renamed in a watched folder triggers an incremental re-scan. A short debounce period (3 seconds) lets file copies and batch moves settle before the scan runs, so copying 50 files in results in one scan, not 50.

**When the app is reopened**, every folder in your library is immediately queued for an incremental scan. Only files whose modification time has changed since the last scan are re-probed with ffprobe — unchanged files are skipped, so startup scans on large libraries are fast.

**Scan queue**: scans run one folder at a time. If multiple folders trigger re-scans simultaneously (for example, all folders on startup), they queue up and run sequentially. The scan indicator in the top bar shows the current folder progress and how many scans are waiting.

No manual rescans are needed for day-to-day library updates. The **Rescan** button remains available if you need to force a full re-probe (for example, after changing the bitrate threshold or AV1 flagging setting).

---

## Presets

The **Presets** tab (accessible from Settings) lets you save and reuse custom encode configurations.

Each preset stores a full set of encode overrides — codec, quality, container, scale height, pixel format, encoder speed, audio action, force stereo, normalization, and subtitle mode. When you open the **Encode** modal, you can load any saved preset with one click, which fills in all the override fields at once.

### Built-in preset: Tower Unite

The **Tower Unite** preset is included by default. It targets VP9 + Opus in WebM, which is the format required for synced playback in Tower Unite condos without CEFCodecFix. Settings:

- Hardware Accelerator: Software (VP9 is always software-encoded)
- Codec: VP9
- Audio: Opus
- Container: WebM
- Quality: 31

---

## Encode

The **Encode** button (bottom-left of the main toolbar) opens a per-batch encode modal. It lets you queue a custom encode for any selected files with settings that override the global defaults for that batch only.

### Per-batch overrides

All video and audio settings available in the Settings panel can be overridden per-batch: codec, quality, container, scale height, pixel format, encoder speed, subtitle mode, force stereo, and loudness normalization.

### Output location

By default, encoded files are saved next to their source files (same directory). You can choose a different output directory using the **Browse** button.

When an output directory is set:
- The output filename is `{original_stem}{ext}` written directly into the chosen directory
- The original file is **always kept** — it is never deleted or replaced, regardless of other settings
- The keep/replace original option is hidden (not applicable)

### Collision warning

If multiple selected files share the same filename stem (name without extension) and would write to the same output directory, Conduit warns you before encoding starts. The warning lists every conflicting group of files. You can go back to change the selection or output directory, or encode anyway (the last file in each group will overwrite earlier ones).

### HDR handling

When the selection contains HDR files, a prompt appears asking whether to remux or re-encode them (same as normal optimization). Non-HDR files in the same batch are always encoded without prompting.

---

## HDR content

When you queue HDR files for optimization, Conduit prompts you to choose:

- **Remux** — rewraps the file into MKV without re-encoding. Preserves full HDR metadata (Dolby Vision, HDR10+). No quality loss.
- **Re-encode** — re-encodes with your configured settings. HDR metadata may be reduced to HDR10.

For HDR content, remux is recommended unless file size reduction is the priority.

---

## Database

The **Database** tab (accessible from Settings) shows all files that Conduit has previously encoded or remuxed. From here you can re-flag individual files (or all of them at once) so they appear again in the optimization queue.

This is useful if you want to re-encode files that were already optimized — for example, after changing your quality settings or switching to a different codec.

---

## Uninstall

```bash
# Remove launcher and desktop entry
rm -f ~/.local/bin/conduit
rm -f ~/.local/share/applications/conduit.desktop

# Remove the app directory (includes venv and database)
rm -rf /path/to/conduit

# If you set up the systemd service
systemctl --user disable --now conduit
rm -f ~/.config/systemd/user/conduit.service
systemctl --user daemon-reload
```

---

## Supported distros

Tested on CachyOS. Should work on any Linux distro with Python 3.10+ and a compatible GPU or CPU. The install script handles package installation for Arch, Debian/Ubuntu, Fedora, and openSUSE. Other distros may require manually installing `python3-gobject` + `webkit2gtk` or `python3-pyqt6` + `qt6-webengine` before running `install.sh`.
