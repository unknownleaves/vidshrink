<p align="center"><img src="icon.png" width="128" alt="VidShrink icon"></p>

<h1 align="center">VidShrink</h1>
<p align="center">A simple video compressor for Windows: shrink a video to the size you want while keeping the quality.</p>


Shrinks videos to a size you choose (for example **1 GB → 500 MB**) while keeping as much quality as possible.

**Features**
- Target size (MB), percent of the original, or constant-quality mode
- Two-pass H.264 / H.265 (HEVC) encoding for the best quality at a given size
- Batch queue with thumbnails: drag and drop files or whole folders, pause and resume, time left
- Dark, modern interface (Qt) that remembers your settings
- Optional downscaling (4K → 1080p, etc.) and adjustable audio bitrate
- Uses your graphics card: GPU decoding, GPU encoding, or CPU and GPU in parallel (NVIDIA, AMD, Intel)
- Downloads FFmpeg automatically on first run
- Updates itself: new versions published here are offered in the app automatically

## Install

Open **PowerShell** (press Start, type `powershell`, press Enter), paste this and press Enter:

```powershell
irm https://raw.githubusercontent.com/unknownleaves/vidshrink/main/install.ps1 | iex
```

It downloads the latest VidShrink, checks the download is genuine, installs it to your user folder (no admin needed), adds Start menu and Desktop shortcuts, and opens the app. Running the same command again updates or repairs the install. To uninstall, go to **Settings → Apps → Installed apps → VidShrink → Uninstall**.

**Manual download:** grab **`VidShrink.exe`** from [**Releases**](https://github.com/unknownleaves/vidshrink/releases/latest) and run it from a folder you own (e.g. Documents). Windows SmartScreen may warn about an unrecognised app the first time. Click **More info → Run anyway**.

**From source:** download **`VidShrink-source.zip`** from the same page, unzip it and follow the quick start below.

## Quick start (source version)

1. Install **Python 3.9 or newer** from https://www.python.org/downloads/ (during setup, tick **"Add python.exe to PATH"**). The first launch installs the interface library (PySide6-Essentials, about 80 MB) automatically.
2. Double-click **`Start VidShrink.bat`**.
3. On first launch, VidShrink offers to download **FFmpeg**, the free encoding engine it uses (about 100 MB, one time only). Click **Yes**.
4. Click **Add Videos…**, choose **Target size = 500 MB** (or any size), then click **▶ Start**.

The compressed file is saved next to the original as `name_compressed.mp4`. You can also choose a different folder under **Save to**.

## Updates

VidShrink checks this repository for a new release a few seconds after it starts. When there is one, it shows what's new and asks whether to install it. Click **Yes**, and it downloads the update, checks that the file is genuine (SHA-256), installs it and restarts. You can also click **⟳ Check for Updates** at any time.

## Desktop & Start menu shortcut

Double-click **`Create Desktop Shortcut.bat`**. It adds a **VidShrink** shortcut with the app icon to your Desktop and Start menu. From then on you can launch the app from there, and pin it to the taskbar.

## Make a standalone .exe (optional)

Double-click **`Build EXE.bat`**. You'll get `dist\VidShrink.exe`, with the VidShrink icon, which runs without Python installed, so you can share it. Afterwards, run `Create Desktop Shortcut.bat` again so your shortcut opens the .exe.

The icon source is `vidshrink.svg`. `vidshrink.ico` contains all the Windows sizes (16–256 px).

## The settings

| Setting | What it does |
|---|---|
| **Target size (MB)** | Gets the file to this size. Uses *two-pass* encoding: the first pass analyses the video, the second spends the bits where they matter (fast motion and detail) for the best quality at that size. |
| **Percent of original** | Same as above, but relative to each file (e.g. 50% = half the size). Handy when you queue many files. |
| **Constant quality** | Ignores size and keeps a fixed visual quality (23 = great, 18 = visually lossless). Gives the smallest file for a given look. |
| **Codec** | **H.264** plays everywhere. **H.265/HEVC** gives noticeably better quality at the same size (or the same quality ~30–40% smaller). It plays on Windows 10/11, phones, modern TVs, YouTube and so on. |
| **Speed / quality** | Slower presets squeeze out more quality at the same size. *Balanced* is a good default; use *High quality* for important videos. |
| **Encoder** | **Auto** (recommended): the CPU encodes for the best quality, while your graphics card (GPU) decodes the original to speed things up. **GPU – fastest**: your graphics card does the encoding too. Often 5–10× faster, with slightly lower quality at the same size. **CPU only**: no GPU at all. |
| **Fast batch** | With several files queued, the CPU and the GPU each compress a file at the same time, so the batch finishes sooner. Files done on the GPU are slightly lower quality. |
| **Resolution** | Downscaling (e.g. 4K → 1080p) is the best way to keep things looking sharp when you need a *much* smaller file. |
| **Audio** | 128 kbps AAC sounds good for most videos. 192 kbps is better for music. |

### Tips for keeping quality
- Halving a file (1 GB → 500 MB) with H.264 usually looks practically identical to the original, because most camera and screen recordings are encoded very inefficiently.
- For heavy shrinking (to 20–30% or less), switch to **H.265** and/or lower the **Resolution**. The log suggests this when a target is very tight.
- Double-click a finished file in the list to show it in Explorer, or right-click it for more options. A file that failed shows the reason on right-click.
- **Pause** stops the encoding completely (no CPU or GPU use) until you click **Resume**.
- Click **Log** at the top to see exactly what VidShrink did, which helps when reporting a problem.

## Notes
- VidShrink detects NVIDIA (NVENC), AMD (AMF) and Intel (Quick Sync) graphics automatically and shows what it found under the Encoder setting. If the GPU can't handle a file, it switches to the CPU by itself.
- Output is always `.mp4` with the first video and audio track. Subtitles and extra audio tracks aren't kept.
- HDR videos are converted to standard (SDR-range 8-bit) output.
- FFmpeg is stored in `%LOCALAPPDATA%\VidShrink\bin`. To use your own copy instead, put `ffmpeg.exe` and `ffprobe.exe` next to `vidshrink.py` or `VidShrink.exe`, or add them to your PATH.

## Publishing an update (for the maintainer)

1. Make your changes, and set a higher version at the top of `vidshrink_core.py`, e.g. `VERSION = "1.2.1"`.
2. Commit and push to `main`.

That's it. GitHub Actions (`.github/workflows/release.yml`) tests the app on Windows by driving the real window, saves screenshots to the `ci-screenshots` branch, builds `VidShrink.exe` and checks that it starts. If all of that passes and the version is new, it packages `VidShrink-source.zip` and `SHA256SUMS.txt` and publishes the release **v1.2.1** with auto-generated notes. A failed test means nothing is published. Pushes that don't change `VERSION` don't publish anything. You can edit the release text on GitHub afterwards: it's what users see under "What's new". You can also start it by hand from the **Actions** tab (**Test & Release → Run workflow**).

Everyone running VidShrink is offered the update the next time they open it. The repository must stay **public** for the update check to work.

## Project layout

| File | What it is |
|---|---|
| `vidshrink.py` | The app window (PySide6 / Qt) |
| `vidshrink_core.py` | The engine: probing, CPU/GPU encoding, FFmpeg setup, self-updates. `VERSION` lives here. |
| `tests/smoke_gui.py` | The Windows UI test the release workflow runs |
| `install.ps1` | The one-line installer |
