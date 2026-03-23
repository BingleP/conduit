# Conduit

A desktop application for scanning your video library, identifying files that would benefit from re-encoding, and re-encoding them using hardware-accelerated ffmpeg — all from a clean, local web-based UI.

---

## What it does

- **Scans** media folders and extracts technical metadata from every video file using `ffprobe`
- **Flags** files that need optimization based on configurable rules (high bitrate, H.264 Hi10P, AV1)
- **Encodes** flagged files using hardware-accelerated ffmpeg, replacing the original in-place
- **Remuxes** files into MKV without re-encoding when appropriate (e.g. HDR content)
- **Filters** audio and subtitle tracks by language, re-encodes lossy audio to Opus/AAC, copies lossless tracks

Runs as a desktop app (native window via pywebview) with an optional Web UI for network access.

---

## Requirements

- Linux (Arch, Debian/Ubuntu, Fedora, openSUSE)
- Python 3.10+
- ffmpeg and ffprobe
- A supported GPU for hardware encoding:
  - **NVIDIA** — GTX 900 series or newer (NVENC)
  - **Intel** — 6th gen Core or newer (Quick Sync)
  - **AMD** — RX 400 series or newer (AMF)

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
| Hardware Accelerator | GPU backend: `nvenc` (NVIDIA), `qsv` (Intel), `amf` (AMD) | `nvenc` |
| ffmpeg Path | Path to ffmpeg binary | `ffmpeg` |
| ffprobe Path | Path to ffprobe binary | `ffprobe` |

### Video

| Setting | Description | Default |
|---|---|---|
| Output Codec | Target codec: HEVC, AV1, or H.264 | `hevc` |
| Quality (CQ/QP) | Encode quality. Lower = better quality, larger file | `24` |

### Audio

| Setting | Description | Default |
|---|---|---|
| Lossy Track Handling | What to do with lossy audio: re-encode to Opus, AAC, or copy | `opus` |
| Keep Audio Languages | Which language tracks to include in the output | `eng`, `jpn` |

Lossless tracks (TrueHD, DTS-HD MA, FLAC, PCM) are always copied regardless of this setting. If no matching language track is found, the first audio track is kept as a fallback.

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

## HDR content

When you queue HDR files for optimization, Conduit prompts you to choose:

- **Remux** — rewraps the file into MKV without re-encoding. Preserves full HDR metadata (Dolby Vision, HDR10+). No quality loss.
- **Re-encode** — re-encodes with your configured settings. HDR metadata may be reduced to HDR10.

For HDR content, remux is recommended unless file size reduction is the priority.

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

Tested on CachyOS. Should work on any Linux distro with Python 3.10+ and a compatible GPU. The install script handles package installation for Arch, Debian/Ubuntu, Fedora, and openSUSE. Other distros may require manually installing `python3-gobject` + `webkit2gtk` or `python3-pyqt6` + `qt6-webengine` before running `install.sh`.
