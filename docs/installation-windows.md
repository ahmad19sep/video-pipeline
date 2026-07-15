# Windows Installation

## Core runtimes

CutMachine requires Python 3.11+, Node.js 20+, Git, FFmpeg, and FFprobe on `PATH`.

On Windows 11, install the currently available Winget FFmpeg package with:

```powershell
winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
```

Open a new PowerShell window after installation, then verify:

```powershell
ffmpeg -version
ffprobe -version
```

## Repository environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Set-Location remotion
npm install
Set-Location ..
python cutmachine.py doctor
```

Missing Faster-Whisper, CUDA, or API keys are warnings in Phase 0. Missing FFmpeg or FFprobe is blocking because later media stages cannot run safely without them.

