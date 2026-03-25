# =============================================================================
# Conduit — Windows Installer (PowerShell)
# =============================================================================
# Run from a PowerShell prompt inside the Conduit directory:
#
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\install.ps1
#
# Requirements:
#   - Windows 10 / 11
#   - Python 3.10 or later  (https://python.org)
#   - ffmpeg in PATH, or configure paths later in Conduit's Settings
#
# Optional flags:
#   -NoShortcut    Skip creating a Start Menu shortcut
# =============================================================================

param(
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
$ConduitDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Info    { Write-Host "[Conduit] $args" -ForegroundColor Cyan    }
function Write-Success { Write-Host "[Conduit] $args" -ForegroundColor Green   }
function Write-Warn    { Write-Host "[Conduit] $args" -ForegroundColor Yellow  }
function Write-Err     { Write-Host "[Conduit] ERROR: $args" -ForegroundColor Red; exit 1 }

# -----------------------------------------------------------------------------
# 1. Find Python 3.10+
# -----------------------------------------------------------------------------
Write-Info "Checking for Python 3.10+..."

$Python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $parts = $ver.Trim().Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $Python = (Get-Command $cmd).Source
                Write-Info "Found $Python ($ver)"
                break
            }
        }
    } catch {}
}

if (-not $Python) {
    Write-Err "Python 3.10+ is required but was not found.`nDownload it from https://python.org and make sure 'Add Python to PATH' is checked."
}

# -----------------------------------------------------------------------------
# 2. Create virtual environment
# -----------------------------------------------------------------------------
$Venv = Join-Path $ConduitDir "venv"
Write-Info "Setting up virtual environment..."

if (-not (Test-Path $Venv)) {
    & $Python -m venv $Venv
    Write-Success "Virtual environment created."
} else {
    Write-Info "Virtual environment already exists, skipping."
}

$VenvPython  = Join-Path $Venv "Scripts\python.exe"
$VenvPythonw = Join-Path $Venv "Scripts\pythonw.exe"
$VenvPip     = Join-Path $Venv "Scripts\pip.exe"

# -----------------------------------------------------------------------------
# 3. Install Python dependencies
# -----------------------------------------------------------------------------
Write-Info "Installing Python dependencies..."
& $VenvPip install --upgrade pip --quiet
& $VenvPip install -r (Join-Path $ConduitDir "requirements.txt") --quiet
Write-Success "Python dependencies installed."

# Verify pywebview has a working backend (Edge WebView2 on Windows)
$webviewOk = & $VenvPython -c "import webview; print('ok')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Err "pywebview failed to import. Check that requirements.txt installed correctly."
}

# -----------------------------------------------------------------------------
# 4. Create launcher scripts
# -----------------------------------------------------------------------------
Write-Info "Creating launcher..."

$LauncherBat = Join-Path $ConduitDir "conduit.bat"

# conduit.bat — GUI launcher (no console window via pythonw)
@"
@echo off
cd /d "%~dp0"
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0desktop.py" %*
"@ | Set-Content -Path $LauncherBat -Encoding ASCII

Write-Success "Launcher created: $LauncherBat"

# -----------------------------------------------------------------------------
# 5. Create Start Menu shortcut
# -----------------------------------------------------------------------------
if (-not $NoShortcut) {
    $StartMenu    = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $ShortcutPath = Join-Path $StartMenu "Conduit.lnk"
    $IconPath     = Join-Path $ConduitDir "frontend\icons\conduit.ico"

    Write-Info "Creating Start Menu shortcut..."

    $WshShell              = New-Object -ComObject WScript.Shell
    $Shortcut              = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath   = $LauncherBat
    $Shortcut.WorkingDirectory = $ConduitDir
    $Shortcut.Description  = "Video library manager and optimizer"
    if (Test-Path $IconPath) { $Shortcut.IconLocation = "$IconPath,0" }
    $Shortcut.Save()

    Write-Success "Start Menu shortcut created: $ShortcutPath"
}

# -----------------------------------------------------------------------------
# 6. Check for ffmpeg
# -----------------------------------------------------------------------------
Write-Info "Checking for ffmpeg..."
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Success "ffmpeg found in PATH."
} else {
    Write-Warn "ffmpeg was not found in PATH."
    Write-Warn "Download it from https://ffmpeg.org/download.html (e.g. the gyan.dev build),"
    Write-Warn "extract it, add the 'bin' folder to your PATH, then restart Conduit."
    Write-Warn "Alternatively, set custom paths in Conduit's Settings after first launch."
}

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
Write-Host ""
Write-Success "Conduit installed successfully!"
Write-Host ""
Write-Host "  Launch:       double-click conduit.bat"
Write-Host "                or search 'Conduit' in the Start Menu"
Write-Host "  Headless:     conduit.bat --no-gui"
Write-Host ""
