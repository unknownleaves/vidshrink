#!/usr/bin/env python3
"""
VidShrink - a simple video compressor for Windows (a mini "Media Encoder").

Shrinks videos to a target file size (e.g. 1 GB -> 500 MB) while keeping as much
quality as possible, using two-pass H.264 / H.265 encoding via FFmpeg.

Requires: Python 3.8+ (with Tkinter, included in the standard Windows installer)
          FFmpeg (the app offers to download it automatically on first run)
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import hashlib
import urllib.error
import urllib.request
import zipfile

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

APP_NAME = "VidShrink"
VERSION = "1.1.0"  # bump this and push to main to publish an update to all users
GITHUB_REPO = "unknownleaves/vidshrink"  # updates are published as GitHub Releases here
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # hide console windows on Windows
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# App icon (PNG, base64) used for the window/taskbar when the .ico file is not available
ICON_PNG_32 = (
    "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"
)
ICON_PNG_64 = (
    "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"
)
MB = 1024 * 1024  # Windows Explorer "MB"
CONTAINER_OVERHEAD = 0.97  # leave ~3% headroom so the file lands at/under the target

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".wmv", ".m4v", ".webm", ".flv",
              ".mts", ".m2ts", ".ts", ".mpg", ".mpeg", ".3gp", ".vob", ".mxf")

CODECS = {
    "H.264 (plays everywhere)": "h264",
    "H.265 / HEVC (best quality per MB)": "h265",
}
PRESETS = {
    "Fast": "fast",
    "Balanced": "medium",
    "High quality (slower)": "slow",
    "Maximum quality (very slow)": "slower",
}
RESOLUTIONS = {
    "Keep original": 0,
    "4K (2160p)": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
}
ENGINES = {
    "Auto – CPU encodes, GPU decodes (best quality)": "auto",
    "GPU – fastest": "gpu",
    "CPU only": "cpu",
}
AUDIO_RATES = {"64 kbps": 64, "96 kbps": 96, "128 kbps": 128, "160 kbps": 160,
               "192 kbps": 192, "256 kbps": 256}

PROGRESS_LINE = re.compile(r"^[a-z0-9_]+=")  # "-progress" key=value lines (values may contain spaces)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def app_dir():
    if getattr(sys, "frozen", False):  # running as a PyInstaller .exe
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """Find a bundled file, both when run as a script and as a PyInstaller .exe."""
    for base in (getattr(sys, "_MEIPASS", None), app_dir()):
        if base and os.path.isfile(os.path.join(base, name)):
            return os.path.join(base, name)
    return None


def tools_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_NAME, "bin")


def find_tool(name):
    for d in (app_dir(), os.path.join(app_dir(), "ffmpeg", "bin"), tools_dir()):
        p = os.path.join(d, name + EXE)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def fmt_size(n):
    if n is None:
        return "-"
    if n >= 1024 * 1024 * MB:
        return f"{n / (1024 * 1024 * MB):.2f} TB"
    if n >= 1024 * MB:
        return f"{n / (1024 * MB):.2f} GB"
    if n >= MB:
        return f"{n / MB:.1f} MB"
    return f"{n / 1024:.0f} KB"


def fmt_dur(sec):
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_rate(r):
    try:
        if "/" in r:
            a, b = r.split("/")
            return float(a) / float(b) if float(b) else 0.0
        return float(r)
    except (ValueError, TypeError):
        return 0.0


def download_ffmpeg(report):
    """Download FFmpeg essentials build for Windows into %LOCALAPPDATA%/VidShrink/bin."""
    dest = tools_dir()
    os.makedirs(dest, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="vidshrink_dl_")
    try:
        zpath = os.path.join(tmp, "ffmpeg.zip")
        req = urllib.request.Request(FFMPEG_ZIP_URL, headers={"User-Agent": f"{APP_NAME}/{VERSION}"})
        with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                report(done, total)
        found = 0
        with zipfile.ZipFile(zpath) as z:
            for member in z.namelist():
                base = os.path.basename(member)
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    with z.open(member) as src, open(os.path.join(dest, base), "wb") as out:
                        shutil.copyfileobj(src, out)
                    found += 1
        if found < 2:
            raise RuntimeError("Downloaded archive did not contain ffmpeg.exe and ffprobe.exe")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------
# Updates (published as GitHub Releases by .github/workflows/release.yml)
# ----------------------------------------------------------------------------

EXE_ASSET = "VidShrink.exe"
SOURCE_ASSET = "VidShrink-source.zip"
CHECKSUM_ASSET = "SHA256SUMS.txt"

# Runs after the .exe has quit: swaps in the new .exe, then restarts it.
UPDATE_BAT = r"""@echo off
chcp 65001 >nul
set n=0
:retry
move /y "{new}" "{exe}" >nul 2>nul
if not errorlevel 1 goto done
set /a n+=1
if %n% geq 60 goto end
ping -n 2 127.0.0.1 >nul
goto retry
:done
start "" "{exe}"
:end
del "%~f0"
"""


def parse_version(v):
    nums = [int(n) for n in re.findall(r"\d+", v or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest_release():
    """Newest published release: dict(version, tag, notes, url, assets{name: download_url})."""
    try:
        with http_get(RELEASES_API, 15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("No updates have been published yet.") from None
        if e.code in (403, 429):
            raise RuntimeError("GitHub is limiting update checks right now. Please try again later.") from None
        raise RuntimeError(f"GitHub returned an error ({e.code}).") from None
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Couldn't reach GitHub ({getattr(e, 'reason', e)}).") from None
    tag = data.get("tag_name") or ""
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "notes": (data.get("body") or "").strip(),
        "url": data.get("html_url"),
        "assets": {a["name"]: a["browser_download_url"] for a in data.get("assets", [])},
    }


def download_file(url, dest, report):
    with http_get(url, 60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            report(done, total)


def verify_checksum(release, name, path):
    """Make sure the download is exactly the file the release workflow built."""
    url = release["assets"].get(CHECKSUM_ASSET)
    if not url:
        raise RuntimeError("This release has no checksum file, so it can't be verified.")
    with http_get(url, 15) as r:
        sums = r.read().decode("utf-8", "replace")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            if parts[0].lower() != h.hexdigest():
                raise RuntimeError("The download was damaged (checksum mismatch). Please try again.")
            return
    raise RuntimeError(f"{name} is not listed in the release checksums.")


def install_update(release, report):
    """Download and stage an update. Returns a function that completes it and restarts the app."""
    tmp = tempfile.mkdtemp(prefix="vidshrink_update_")
    try:
        if getattr(sys, "frozen", False):
            # ---- running as VidShrink.exe: swap the .exe after we exit ----
            url = release["assets"].get(EXE_ASSET)
            if not url:
                raise RuntimeError(f"This release has no {EXE_ASSET} to download.")
            dl = os.path.join(tmp, EXE_ASSET)
            download_file(url, dl, report)
            verify_checksum(release, EXE_ASSET, dl)
            exe = sys.executable
            new = exe + ".new"
            try:
                shutil.move(dl, new)
            except OSError as e:
                raise RuntimeError(f"Can't write to {os.path.dirname(exe)} ({e.strerror}). Move VidShrink.exe "
                                   "to a folder you can write to (e.g. Documents) and try again.") from None
            bat = os.path.join(tempfile.gettempdir(), "vidshrink_update.bat")
            with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(UPDATE_BAT.format(new=new, exe=exe))

            def finish():
                subprocess.Popen(["cmd", "/c", bat], close_fds=True,
                                 creationflags=NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            return finish

        # ---- running from source (Start VidShrink.bat): replace the app files ----
        url = release["assets"].get(SOURCE_ASSET)
        if not url:
            raise RuntimeError(f"This release has no {SOURCE_ASSET} to download.")
        dl = os.path.join(tmp, SOURCE_ASSET)
        download_file(url, dl, report)
        verify_checksum(release, SOURCE_ASSET, dl)
        out = os.path.join(tmp, "src")
        with zipfile.ZipFile(dl) as z:
            z.extractall(out)
        root = next((d for d, _, files in os.walk(out) if "vidshrink.py" in files), None)
        if not root:
            raise RuntimeError("The update package is missing vidshrink.py.")
        dest = app_dir()
        for name in os.listdir(root):
            src = os.path.join(root, name)
            if os.path.isfile(src) and not name.startswith("."):
                staged = os.path.join(dest, name + ".updating")
                shutil.copy2(src, staged)
                os.replace(staged, os.path.join(dest, name))

        def finish():
            py = sys.executable
            pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
            if IS_WIN and os.path.isfile(pyw):
                py = pyw  # relaunch without a console window
            subprocess.Popen([py, os.path.join(dest, "vidshrink.py")], cwd=dest, close_fds=True)
        return finish
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe(ffprobe, path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "Could not read file")
    info = json.loads(res.stdout or "{}")
    fmt = info.get("format", {})
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        raise RuntimeError("No video stream found")
    duration = float(fmt.get("duration") or v.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("Could not determine video duration")
    return {
        "duration": duration,
        "size": os.path.getsize(path),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": parse_rate(v.get("avg_frame_rate")) or parse_rate(v.get("r_frame_rate")) or 30.0,
        "vcodec": v.get("codec_name", "?"),
        "v_index": v["index"],
        "a_index": a["index"] if a else None,
    }


def target_bytes(info, s):
    """Target output size in bytes, or None for constant-quality mode."""
    if s["mode"] == "size":
        return int(s["size_mb"] * MB)
    if s["mode"] == "percent":
        return int(info["size"] * s["percent"] / 100.0)
    return None


def unique_output_path(src, outdir):
    folder = outdir or os.path.dirname(src)
    stem = os.path.splitext(os.path.basename(src))[0]
    path = os.path.join(folder, f"{stem}_compressed.mp4")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem}_compressed ({n}).mp4")
        n += 1
    return path


class Cancelled(Exception):
    pass


def first_line(err):
    """The first, most specific error line, without FFmpeg's "[encoder @ 0x...]" prefix."""
    lines = [re.sub(r"^\[[^\]]*@ 0x[0-9a-f]+\]\s*", "", ln).strip() for ln in str(err).splitlines()]
    lines = [ln for ln in lines if ln]
    return (lines[0] if lines else "unknown error")[:160]


# ----------------------------------------------------------------------------
# GPU support (NVIDIA NVENC, AMD AMF, Intel Quick Sync)
# ----------------------------------------------------------------------------

HWDEC = ["-hwaccel", "auto"]  # GPU decoding; FFmpeg falls back to the CPU for formats the GPU can't decode

GPU_VENDORS = (  # checked in this order; the first that works is used
    ("nvidia", "NVIDIA (NVENC)", "h264_nvenc", "hevc_nvenc"),
    ("amd", "AMD (AMF)", "h264_amf", "hevc_amf"),
    ("intel", "Intel (Quick Sync)", "h264_qsv", "hevc_qsv"),
)


def detect_gpu(ffmpeg):
    """Find a GPU encoder that actually works on this PC by encoding a few test frames.
    Returns {"vendor", "name", "h264": encoder|None, "h265": encoder|None} or None."""
    try:
        listing = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
                                 timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None

    def works(enc):
        if not re.search(rf"\s{enc}\s", listing):
            return False
        try:
            r = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                 "color=c=black:s=1280x720:r=30", "-frames:v", "10", "-c:v", enc, "-pix_fmt", "nv12",
                 "-f", "null", "-"],
                capture_output=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=45)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    for vendor, name, h264, hevc in GPU_VENDORS:
        ok264, ok265 = works(h264), works(hevc)
        if ok264 or ok265:
            return {"vendor": vendor, "name": name,
                    "h264": h264 if ok264 else None, "h265": hevc if ok265 else None}
    return None


def gpu_video_args(gpu, s, v_k, full):
    """Encoder settings for the GPU. full=False is a conservative set for older GPUs/drivers."""
    codec = s["codec"]
    enc = gpu[codec]
    level = {"fast": 0, "medium": 1, "slow": 2, "slower": 3}.get(s["preset"], 1)
    q = s["crf"] + (4 if codec == "h265" else 2)  # roughly matches the CPU quality slider
    rate = ["-b:v", f"{v_k}k", "-maxrate", f"{int(v_k * 1.5)}k", "-bufsize", f"{v_k * 2}k"] if v_k else []
    a = ["-c:v", enc, "-pix_fmt", "nv12"]
    vendor = gpu["vendor"]
    if vendor == "nvidia":
        a += ["-preset", ("p4", "p5", "p6", "p7")[level], "-tune", "hq", "-rc", "vbr"]
        a += rate if v_k else ["-cq", str(q), "-b:v", "0"]
        if full:
            a += ["-multipass", "fullres", "-spatial-aq", "1", "-temporal-aq", "1",
                  "-rc-lookahead", "32", "-bf", "3"]
    elif vendor == "amd":
        a += ["-quality", ("speed", "balanced", "quality", "quality")[level]]
        a += (["-rc", "vbr_peak"] + rate) if v_k else ["-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q)]
        if full:
            a += ["-vbaq", "1", "-preanalysis", "1"]
    else:  # intel
        a += ["-preset", ("faster", "medium", "slow", "veryslow")[level]]
        a += rate if v_k else ["-global_quality", str(q)]
        if full:
            a += ["-extbrc", "1", "-look_ahead_depth", "40"]
    if codec == "h265":
        a += ["-tag:v", "hvc1"]
    return a


# ----------------------------------------------------------------------------
# Encoding engine
# ----------------------------------------------------------------------------

class Encoder:
    def __init__(self, ffmpeg, log):
        self.ffmpeg = ffmpeg
        self.log = log
        self.proc = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass

    def _run(self, args, cwd, duration, on_progress):
        cmd = [self.ffmpeg, "-hide_banner", "-y", "-nostdin", "-nostats",
               "-loglevel", "error", "-progress", "pipe:1"] + args
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW, bufsize=1)
        errors = []
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    t = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                on_progress(min(max(t / duration, 0.0), 1.0))
            elif PROGRESS_LINE.match(line):
                continue
            else:
                errors.append(line)
        rc = self.proc.wait()
        self.proc = None
        if self.cancelled:
            raise Cancelled()
        if rc != 0:
            raise RuntimeError("\n".join(errors[-8:]) or f"FFmpeg exited with code {rc}")

    def encode(self, src, info, s, outdir, on_progress, engine="cpu", hwdecode=False):
        """Encode one file on the "cpu" or "gpu" engine. Returns (output_path, output_size) or raises."""
        dur = info["duration"]
        has_audio = info["a_index"] is not None
        a_k = s["audio_kbps"] if has_audio else 0
        tgt = target_bytes(info, s)

        if tgt is not None and tgt >= info["size"]:
            raise RuntimeError(f"Already smaller than the target ({fmt_size(info['size'])}) – skipped")

        # --- output dimensions -------------------------------------------
        w, h = info["width"], info["height"]
        vf = []
        limit = s["height"]
        if limit and min(w, h) > limit:
            if w >= h:
                vf = ["-vf", f"scale=-2:{limit}:flags=lanczos"]
                w, h = int(w * limit / h), limit
            else:  # portrait video: limit the width (short side)
                vf = ["-vf", f"scale={limit}:-2:flags=lanczos"]
                w, h = limit, int(h * limit / w)

        # --- bitrate plan ------------------------------------------------
        v_k = None
        if tgt is not None:
            total_k = tgt * 8 / 1000.0 / dur * CONTAINER_OVERHEAD
            v_k = total_k - a_k
            if has_audio and v_k < 400 and a_k > 64:
                a_k = 64
                v_k = total_k - a_k
                self.log("  Target is tight – audio lowered to 64 kbps to give video more room.")
            if v_k < 60:
                raise RuntimeError(f"Target is too small for a {fmt_dur(dur)} video "
                                   f"(would leave only {max(v_k, 0):.0f} kbps for video). Pick a larger size.")
            v_k = int(v_k)
            bpp = v_k * 1000.0 / max(w * h * info["fps"], 1)
            min_bpp = 0.035 if s["codec"] == "h264" else 0.022
            self.log(f"  Video bitrate: {v_k} kbps, audio: {a_k if has_audio else 0} kbps"
                     f" -> {w}x{h} @ {info['fps']:.2f} fps")
            if bpp < min_bpp:
                self.log("  Tip: this is a lot of compression for this resolution. If it looks soft or blocky, "
                         "try H.265 or lowering the resolution (e.g. 1080p/720p).")

        # --- common args -------------------------------------------------
        maps = ["-map", f"0:{info['v_index']}"]
        if has_audio:
            maps += ["-map", f"0:{info['a_index']}"]
        audio = ["-c:a", "aac", "-b:a", f"{a_k}k"] if has_audio else ["-an"]
        tail = ["-map_metadata", "0", "-movflags", "+faststart"]

        out_path = unique_output_path(src, outdir)
        part_path = os.path.splitext(out_path)[0] + ".partial.mp4"
        workdir = tempfile.mkdtemp(prefix="vidshrink_")  # holds two-pass log files
        ctx = dict(src=src, dur=dur, maps=maps, vf=vf, audio=audio, tail=tail, v_k=v_k, tgt=tgt,
                   out=part_path, cwd=workdir, on_progress=on_progress)
        gpu = s.get("gpu")
        try:
            if engine == "gpu" and gpu and gpu.get(s["codec"]):
                try:
                    self._encode_gpu(ctx, s, gpu)
                except Cancelled:
                    raise
                except RuntimeError as e:
                    self.log(f"  GPU encoding didn't work ({first_line(e)}) – using the CPU instead.")
                    self._encode_cpu(ctx, s, hwdecode=True)
            else:
                if engine == "gpu":
                    self.log("  No usable GPU encoder for this codec – using the CPU instead.")
                self._encode_cpu(ctx, s, hwdecode=hwdecode or engine == "gpu")
            os.replace(part_path, out_path)
        except BaseException:
            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except OSError:
                pass
            raise
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        size = os.path.getsize(out_path)
        if tgt is not None and size > tgt * 1.03:
            self.log(f"  Note: output is {fmt_size(size)}, slightly over the {fmt_size(tgt)} target.")
        return out_path, size

    def _try_variants(self, variants, run, labels):
        """Run with each variant in turn until one works (e.g. GPU decoding, then CPU decoding)."""
        for i, v in enumerate(variants):
            try:
                return run(v)
            except Cancelled:
                raise
            except RuntimeError as e:
                if i == len(variants) - 1:
                    raise
                self.log(f"  {labels[i]} didn't work ({first_line(e)}) – retrying with {labels[i + 1]}…")

    def _encode_cpu(self, ctx, s, hwdecode):
        """x264/x265 on the CPU: best quality per MB. Optionally the GPU decodes the source."""
        codec, preset = s["codec"], s["preset"]
        if codec == "h264":
            vcodec = ["-c:v", "libx264", "-preset", preset, "-pix_fmt", "yuv420p"]
        else:
            vcodec = ["-c:v", "libx265", "-preset", preset, "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
        src, dur, cwd, v_k = ctx["src"], ctx["dur"], ctx["cwd"], ctx["v_k"]
        maps, vf, audio, tail, out, on_progress = (ctx[k] for k in ("maps", "vf", "audio", "tail", "out",
                                                                     "on_progress"))

        def run(hw):
            inp = hw + ["-i", src]
            if v_k is None:
                # ---- constant quality (single pass) ----
                crf = s["crf"] + (5 if codec == "h265" else 0)  # x265 CRF scale is ~5 higher for same look
                q = ["-crf", str(crf)]
                if codec == "h265":
                    q += ["-x265-params", "log-level=error"]
                self._run(inp + maps + vf + vcodec + q + audio + tail + [out], cwd, dur, on_progress)
                return
            # ---- two-pass to hit the target size ----
            rate = ["-b:v", f"{v_k}k"]
            if codec == "h264":
                p1 = rate + ["-pass", "1", "-passlogfile", "pass"]
                p2 = rate + ["-pass", "2", "-passlogfile", "pass"]
            else:  # relative stats path avoids x265 choking on "C:" colons
                p1 = rate + ["-x265-params", "pass=1:stats=pass.log:log-level=error"]
                p2 = rate + ["-x265-params", "pass=2:stats=pass.log:log-level=error"]
            self.log("  Pass 1/2 (analysing)…")
            self._run(inp + maps[:2] + vf + vcodec + p1 + ["-an", "-f", "null", os.devnull],
                      cwd, dur, lambda f: on_progress(0.35 * f))
            self.log("  Pass 2/2 (encoding)…")
            self._run(inp + maps + vf + vcodec + p2 + audio + tail + [out],
                      cwd, dur, lambda f: on_progress(0.35 + 0.65 * f))

        if hwdecode:
            self.log("  CPU encoding, GPU decoding")
            self._try_variants([HWDEC, []], run, ["GPU decoding", "CPU decoding"])
        else:
            self.log("  CPU encoding")
            run([])

    def _encode_gpu(self, ctx, s, gpu):
        """Hardware encoder on the GPU: much faster, slightly less quality per MB."""
        self.log(f"  GPU encoding on {gpu['name']}")
        tgt, v_k = ctx["tgt"], ctx["v_k"]

        def run(variant, rate=v_k):
            full, hw = variant
            args = ((HWDEC if hw else []) + ["-i", ctx["src"]] + ctx["maps"] + ctx["vf"]
                    + gpu_video_args(gpu, s, rate, full) + ctx["audio"] + ctx["tail"] + [ctx["out"]])
            self._run(args, ctx["cwd"], ctx["dur"], ctx["on_progress"])
            return variant

        variant = self._try_variants(
            [(True, True), (False, True), (False, False)], run,
            ["tuned GPU settings", "basic GPU settings", "basic GPU settings with CPU decoding"])

        # GPU encoders can't do true two-pass, so correct an overshoot with one more (fast) pass
        if tgt and v_k:
            size = os.path.getsize(ctx["out"])
            if size > tgt * 1.02:
                new_k = max(int(v_k * tgt / size * 0.97), 60)
                self.log(f"  GPU result was {fmt_size(size)} – re-encoding at {new_k} kbps to fit the target…")
                run(variant, new_k)


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION} – Video Compressor")
        self.geometry("1000x720")
        self.minsize(880, 620)
        self._set_icon()
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.configure("Treeview", rowheight=24)

        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        self.jobs = {}       # iid -> job dict
        self.msgs = queue.Queue()
        self.worker = None      # truthy while compressing
        self.encoders = []      # one Encoder per lane (CPU and/or GPU)
        self.gpu = None         # detected GPU encoder info
        self.gpu_checked = False
        self.active = {}        # iid -> progress fraction of files being encoded right now
        self.total = 0
        self.completed = 0

        self._make_vars()
        self._build_ui()
        self._update_mode()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        self.after(400, self._check_ffmpeg)
        self.updating = False
        self.after(2500, lambda: self._check_updates(manual=False))

    def _set_icon(self):
        try:  # PNG icons work everywhere (title bar, Alt+Tab)
            self._icons = [tk.PhotoImage(data=ICON_PNG_64), tk.PhotoImage(data=ICON_PNG_32)]
            self.iconphoto(True, *self._icons)
        except tk.TclError:
            pass
        ico = resource_path("vidshrink.ico")
        if IS_WIN and ico:  # multi-size .ico gives the crispest taskbar icon on Windows
            try:
                self.iconbitmap(default=ico)
            except tk.TclError:
                pass

    # ---- state ---------------------------------------------------------
    def _make_vars(self):
        self.mode = tk.StringVar(value="size")
        self.size_mb = tk.StringVar(value="500")   # the number typed in the target box
        self.size_unit = tk.StringVar(value="MB")
        self.percent = tk.StringVar(value="50")
        self.crf = tk.IntVar(value=23)
        self.codec = tk.StringVar(value=list(CODECS)[0])
        self.preset = tk.StringVar(value="Balanced")
        self.res = tk.StringVar(value="Keep original")
        self.audio = tk.StringVar(value="128 kbps")
        self.outdir = tk.StringVar(value="")
        self.engine = tk.StringVar(value=list(ENGINES)[0])
        self.fast_batch = tk.BooleanVar(value=False)
        for v in (self.size_mb, self.size_unit, self.percent, self.mode):
            v.trace_add("write", lambda *_: self._refresh_estimates())
        self.mode.trace_add("write", lambda *_: self._update_mode())

    def settings(self):
        try:  # no upper limit: any size works, in MB or GB
            size_mb = float(self.size_mb.get().replace(",", "").strip())
            if self.size_unit.get() == "GB":
                size_mb *= 1024
        except ValueError:
            size_mb = 0
        try:
            percent = float(self.percent.get())
        except ValueError:
            percent = 0
        return {
            "mode": self.mode.get(),
            "size_mb": size_mb,
            "percent": percent,
            "crf": int(self.crf.get()),
            "codec": CODECS[self.codec.get()],
            "preset": PRESETS[self.preset.get()],
            "height": RESOLUTIONS[self.res.get()],
            "audio_kbps": AUDIO_RATES[self.audio.get()],
            "engine": ENGINES[self.engine.get()],
            "fast_batch": bool(self.fast_batch.get()),
            "gpu": self.gpu,
        }

    # ---- layout --------------------------------------------------------
    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        # Toolbar
        bar = ttk.Frame(root)
        bar.pack(fill="x")
        ttk.Button(bar, text="➕ Add Videos…", command=self._add_files).pack(side="left")
        ttk.Button(bar, text="📁 Add Folder…", command=self._add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="Remove Selected", command=self._remove_selected).pack(side="left")
        ttk.Button(bar, text="Clear List", command=self._clear).pack(side="left", padx=6)
        ttk.Label(bar, text=f"v{VERSION}", foreground="#666").pack(side="right")
        self.update_btn = ttk.Button(bar, text="⟳ Check for Updates",
                                     command=lambda: self._check_updates(manual=True))
        self.update_btn.pack(side="right", padx=6)
        ttk.Label(bar, text="Tip: double-click a finished file to show it in Explorer",
                  foreground="#666").pack(side="right", padx=(0, 6))

        # Queue
        qf = ttk.Frame(root)
        qf.pack(fill="both", expand=True, pady=(8, 8))
        cols = ("file", "length", "res", "size", "target", "status")
        self.tree = ttk.Treeview(qf, columns=cols, show="headings", selectmode="extended", height=8)
        for c, t, w, anchor in (("file", "File", 300, "w"), ("length", "Length", 70, "center"),
                                ("res", "Resolution", 95, "center"), ("size", "Original", 90, "e"),
                                ("target", "Target", 110, "e"), ("status", "Status", 230, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c in ("file", "status")))
        sb = ttk.Scrollbar(qf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._reveal)
        self.tree.bind("<Delete>", lambda e: self._remove_selected())

        # Settings
        sf = ttk.LabelFrame(root, text="  Compression settings  ", padding=10)
        sf.pack(fill="x")
        self.setting_widgets = []

        ttk.Label(sf, text="Shrink to:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        modes = ttk.Frame(sf)
        modes.grid(row=0, column=1, columnspan=5, sticky="w", pady=(0, 6))
        r1 = ttk.Radiobutton(modes, text="Target size", variable=self.mode, value="size")
        r1.pack(side="left")
        self.size_spin = ttk.Spinbox(modes, from_=1, to=10 ** 12, increment=50, width=9, textvariable=self.size_mb)
        self.size_spin.pack(side="left", padx=(4, 2))
        self.unit_combo = ttk.Combobox(modes, textvariable=self.size_unit, values=("MB", "GB"),
                                       state="readonly", width=4)
        self.unit_combo.pack(side="left", padx=(0, 18))
        self.unit_combo.bind("<<ComboboxSelected>>", lambda e: self.size_spin.configure(
            increment=1 if self.size_unit.get() == "GB" else 50))
        r2 = ttk.Radiobutton(modes, text="Percent of original", variable=self.mode, value="percent")
        r2.pack(side="left")
        self.pct_spin = ttk.Spinbox(modes, from_=1, to=99, increment=5, width=5, textvariable=self.percent)
        self.pct_spin.pack(side="left", padx=(4, 2))
        ttk.Label(modes, text="%").pack(side="left", padx=(0, 18))
        r3 = ttk.Radiobutton(modes, text="Constant quality", variable=self.mode, value="quality")
        r3.pack(side="left")
        self.crf_scale = ttk.Scale(modes, from_=16, to=32, orient="horizontal", length=120,
                                   command=lambda v: (self.crf.set(int(float(v))), self._crf_text()))
        self.crf_scale.set(23)
        self.crf_scale.pack(side="left", padx=(6, 4))
        self.crf_label = ttk.Label(modes, width=22)
        self.crf_label.pack(side="left")
        self._crf_text()
        self.setting_widgets += [r1, r2, r3, self.size_spin, self.unit_combo, self.pct_spin, self.crf_scale]

        def combo(row, col, label, var, values, width=30):
            ttk.Label(sf, text=label).grid(row=row, column=col, sticky="w", padx=(0 if col == 0 else 20, 6), pady=3)
            cb = ttk.Combobox(sf, textvariable=var, values=list(values), state="readonly", width=width)
            cb.grid(row=row, column=col + 1, sticky="w", pady=3)
            self.setting_widgets.append(cb)
            return cb

        combo(1, 0, "Codec:", self.codec, CODECS)
        combo(1, 2, "Speed / quality:", self.preset, PRESETS, 26)
        combo(2, 0, "Resolution:", self.res, RESOLUTIONS)
        combo(2, 2, "Audio:", self.audio, AUDIO_RATES, 26)
        combo(3, 0, "Encoder:", self.engine, ENGINES, 40)
        gf = ttk.Frame(sf)
        gf.grid(row=3, column=2, columnspan=4, sticky="w", padx=(20, 0), pady=3)
        self.batch_chk = ttk.Checkbutton(gf, text="Fast batch: CPU and GPU each work on a file at once",
                                         variable=self.fast_batch)
        self.batch_chk.pack(side="left")
        self.setting_widgets.append(self.batch_chk)
        self.gpu_label = ttk.Label(sf, text="GPU: checking…", foreground="#666")
        self.gpu_label.grid(row=4, column=1, columnspan=5, sticky="w")

        ttk.Label(sf, text="Save to:").grid(row=5, column=0, sticky="w", pady=(6, 0))
        of = ttk.Frame(sf)
        of.grid(row=5, column=1, columnspan=5, sticky="we", pady=(6, 0))
        self.out_entry = ttk.Entry(of, textvariable=self.outdir, width=60)
        self.out_entry.pack(side="left", fill="x", expand=True)
        b1 = ttk.Button(of, text="Browse…", command=self._pick_outdir)
        b1.pack(side="left", padx=6)
        b2 = ttk.Button(of, text="Same as source", command=lambda: self.outdir.set(""))
        b2.pack(side="left")
        self.setting_widgets += [self.out_entry, b1, b2]
        ttk.Label(sf, text="(leave empty to save next to the original as  name_compressed.mp4)",
                  foreground="#666").grid(row=6, column=1, columnspan=5, sticky="w")

        # Progress + actions
        pf = ttk.Frame(root)
        pf.pack(fill="x", pady=(10, 4))
        self.status = ttk.Label(pf, text="Add videos to get started.")
        self.status.grid(row=0, column=0, sticky="w")
        self.cur_bar = ttk.Progressbar(pf, maximum=1000)
        self.cur_bar.grid(row=1, column=0, sticky="we", pady=2)
        self.all_label = ttk.Label(pf, text="Overall")
        self.all_label.grid(row=2, column=0, sticky="w")
        self.all_bar = ttk.Progressbar(pf, maximum=1000)
        self.all_bar.grid(row=3, column=0, sticky="we", pady=2)
        pf.columnconfigure(0, weight=1)
        btns = ttk.Frame(pf)
        btns.grid(row=0, column=1, rowspan=4, padx=(12, 0))
        self.start_btn = ttk.Button(btns, text="▶  Start", style="Big.TButton", command=self._start)
        self.start_btn.pack(fill="x")
        self.cancel_btn = ttk.Button(btns, text="■  Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(fill="x", pady=(6, 0))

        # Log
        self.logbox = ScrolledText(root, height=7, font=("Consolas", 9), state="disabled", wrap="word")
        self.logbox.pack(fill="both", pady=(6, 0))

    def _crf_text(self):
        v = int(self.crf.get())
        desc = ("visually lossless" if v <= 18 else "excellent" if v <= 21 else
                "great (default)" if v <= 24 else "good, smaller" if v <= 27 else "small file")
        self.crf_label.configure(text=f"{v} – {desc}")

    def _update_mode(self):
        m = self.mode.get()
        if self.worker:
            return
        self.size_spin.configure(state="normal" if m == "size" else "disabled")
        self.unit_combo.configure(state="readonly" if m == "size" else "disabled")
        self.pct_spin.configure(state="normal" if m == "percent" else "disabled")
        self.crf_scale.state(["!disabled"] if m == "quality" else ["disabled"])
        self.batch_chk.state(["!disabled"] if self.gpu else ["disabled"])

    def _show_active(self):
        names = [os.path.basename(self.jobs[i]["path"]) for i in self.active if i in self.jobs]
        if len(names) == 1:
            self.status.configure(text=f"Compressing {names[0]}")
        elif names:
            self.status.configure(text=f"Compressing {len(names)} files at once: " + ", ".join(names))

    def _detect_gpu(self):
        if not self.ffmpeg or self.gpu_checked:
            return
        self.gpu_label.configure(text="GPU: checking…")
        threading.Thread(target=lambda: self.msgs.put(("gpu", detect_gpu(self.ffmpeg))), daemon=True).start()

    # ---- queue management ---------------------------------------------
    def log(self, text):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose videos to compress",
            filetypes=[("Video files", " ".join("*" + e for e in VIDEO_EXTS)), ("All files", "*.*")])
        self._add_paths(paths)

    def _add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder of videos")
        if d:
            paths = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(VIDEO_EXTS)]
            if not paths:
                messagebox.showinfo(APP_NAME, "No video files found in that folder.")
            self._add_paths(paths)

    def _add_paths(self, paths):
        if not paths:
            return
        if not self.ffprobe:
            self._check_ffmpeg()
            return
        existing = {j["path"] for j in self.jobs.values()}
        for p in paths:
            p = os.path.normpath(p)
            if p in existing:
                continue
            iid = self.tree.insert("", "end", values=(os.path.basename(p), "…", "…", "…", "…", "Reading…"))
            self.jobs[iid] = {"path": p, "info": None, "status": "reading", "out": None}
            threading.Thread(target=self._probe_worker, args=(iid, p), daemon=True).start()

    def _probe_worker(self, iid, path):
        try:
            self.msgs.put(("probed", iid, probe(self.ffprobe, path)))
        except Exception as e:  # noqa: BLE001
            self.msgs.put(("probe_failed", iid, str(e)))

    def _remove_selected(self):
        if self.worker:
            return
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.jobs.pop(iid, None)

    def _clear(self):
        if self.worker:
            return
        self.tree.delete(*self.tree.get_children())
        self.jobs.clear()

    def _pick_outdir(self):
        d = filedialog.askdirectory(title="Save compressed videos to…")
        if d:
            self.outdir.set(os.path.normpath(d))

    def _target_text(self, info):
        try:
            s = self.settings()
        except (tk.TclError, KeyError):
            return "-"
        t = target_bytes(info, s)
        if t is None:
            return "Quality mode"
        if t >= info["size"]:
            return "≥ original"
        return fmt_size(t)

    def _refresh_estimates(self):
        if not hasattr(self, "tree"):
            return
        for iid, j in self.jobs.items():
            if j["info"]:
                self.tree.set(iid, "target", self._target_text(j["info"]))

    def _reveal(self, _event):
        iid = self.tree.focus()
        j = self.jobs.get(iid)
        path = j and (j["out"] or j["path"])
        if path and os.path.exists(path) and IS_WIN:
            subprocess.Popen(["explorer", "/select,", path])

    # ---- running -------------------------------------------------------
    def _validate(self, s):
        if s["mode"] == "size" and s["size_mb"] <= 0:
            return "Please enter a target size in MB (e.g. 500)."
        if s["mode"] == "percent" and not (1 <= s["percent"] < 100):
            return "Please enter a percentage between 1 and 99."
        out = self.outdir.get().strip()
        if out and not os.path.isdir(out):
            return f"The output folder does not exist:\n{out}"
        return None

    def _start(self):
        if not self.ffmpeg:
            self._check_ffmpeg()
            return
        s = self.settings()
        err = self._validate(s)
        if err:
            messagebox.showwarning(APP_NAME, err)
            return
        todo = [iid for iid in self.tree.get_children()
                if self.jobs[iid]["info"] and self.jobs[iid]["status"] in ("ready", "failed", "cancelled")]
        if not todo:
            messagebox.showinfo(APP_NAME, "Nothing to do – add some videos first.")
            return
        self.total, self.completed = len(todo), 0
        self.active = {}
        outdir = self.outdir.get().strip()

        # Which engines ("lanes") work through the queue
        gpu_ok = bool(s["gpu"] and s["gpu"].get(s["codec"]))
        if s["fast_batch"] and gpu_ok and len(todo) > 1:
            lanes = [("cpu", "[CPU] "), ("gpu", "[GPU] ")]
        elif s["engine"] == "gpu":
            lanes = [("gpu", "")]
        else:
            lanes = [("cpu", "")]
        if s["fast_batch"] and not gpu_ok:
            self.log("Fast batch needs a supported GPU for this codec – running on the CPU only.")

        jobs = queue.Queue()
        for iid in todo:
            jobs.put(iid)
        self.encoders = []
        self.lanes_left, self.ok_count = len(lanes), 0
        self._set_running(True)
        self.worker = True
        self.log(f"=== Starting {len(todo)} file(s)"
                 + (" – CPU and GPU in parallel" if len(lanes) > 1 else "") + " ===")
        for engine, tag in lanes:
            enc = Encoder(self.ffmpeg, lambda t, tag=tag: self.msgs.put(("log", tag + t)))
            self.encoders.append(enc)
            threading.Thread(target=self._work, args=(enc, engine, tag, jobs, s, outdir), daemon=True).start()

    def _work(self, enc, engine, tag, jobs, s, outdir):
        ok = 0
        hwdecode = s["engine"] != "cpu"  # Auto/GPU: let the GPU decode the source
        while not enc.cancelled:
            try:
                iid = jobs.get_nowait()
            except queue.Empty:
                break
            j = self.jobs.get(iid)
            if not j:
                continue
            self.msgs.put(("status", iid, f"{tag}Encoding… 0%", "running"))
            self.msgs.put(("log", f"{tag}▶ {os.path.basename(j['path'])}  ({fmt_size(j['info']['size'])}, "
                                  f"{fmt_dur(j['info']['duration'])})"))
            try:
                out, size = enc.encode(
                    j["path"], j["info"], s, outdir,
                    lambda f, iid=iid: self.msgs.put(("progress", iid, f, tag)),
                    engine=engine, hwdecode=hwdecode)
                saved = 100 - size * 100.0 / j["info"]["size"]
                self.msgs.put(("finished", iid, out, size, saved))
                ok += 1
            except Cancelled:
                self.msgs.put(("status", iid, "Cancelled", "cancelled"))
                self.msgs.put(("log", f"{tag}  Cancelled."))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                state = "skipped" if "skipped" in msg else "failed"
                self.msgs.put(("status", iid, "Skipped" if state == "skipped" else "Failed", state))
                self.msgs.put(("log", f"{tag}  ✖ {msg}"))
            self.msgs.put(("step", iid))
        # anything left in the queue after a cancel stays "Ready"
        self.msgs.put(("lane_done", ok))

    def _cancel(self):
        if self.encoders:
            for enc in self.encoders:
                enc.cancel()
            self.status.configure(text="Cancelling…")

    def _set_running(self, running):
        st = "disabled" if running else "normal"
        self.start_btn.configure(state=st)
        self.cancel_btn.configure(state="normal" if running else "disabled")
        for w in self.setting_widgets:
            if isinstance(w, ttk.Combobox):
                w.configure(state="disabled" if running else "readonly")
            elif isinstance(w, ttk.Scale):
                w.state(["disabled"] if running else ["!disabled"])
            else:
                w.configure(state=st)
        if not running:
            self.worker = None
            self._update_mode()

    def _poll(self):
        try:
            while True:
                m = self.msgs.get_nowait()
                kind = m[0]
                if kind == "probed":
                    _, iid, info = m
                    if iid in self.jobs:
                        self.jobs[iid].update(info=info, status="ready")
                        self.tree.item(iid, values=(
                            os.path.basename(self.jobs[iid]["path"]), fmt_dur(info["duration"]),
                            f"{info['width']}x{info['height']}", fmt_size(info["size"]),
                            self._target_text(info), f"Ready  ({info['vcodec']})"))
                        self.status.configure(text=f"{len(self.jobs)} video(s) in the list.")
                elif kind == "probe_failed":
                    _, iid, err = m
                    if iid in self.jobs:
                        self.jobs[iid]["status"] = "invalid"
                        self.tree.set(iid, "status", "Can't read file")
                        self.log(f"✖ {os.path.basename(self.jobs[iid]['path'])}: {err}")
                elif kind == "status":
                    _, iid, text, state = m
                    if iid in self.jobs:
                        self.jobs[iid]["status"] = state
                        self.tree.set(iid, "status", text)
                        if state == "running":
                            self.tree.see(iid)
                            self.active[iid] = 0.0
                            self._show_active()
                elif kind == "progress":
                    _, iid, f, tag = m
                    if iid in self.active:
                        self.active[iid] = f
                    if self.active:
                        self.cur_bar["value"] = sum(self.active.values()) / len(self.active) * 1000
                    self.all_bar["value"] = (self.completed + sum(self.active.values())) / max(self.total, 1) * 1000
                    if iid in self.jobs:
                        self.tree.set(iid, "status", f"{tag}Encoding… {f * 100:.0f}%")
                    self.all_label.configure(text=f"Overall  –  {self.completed} of {self.total} done")
                elif kind == "finished":
                    _, iid, out, size, saved = m
                    if iid in self.jobs:
                        self.jobs[iid].update(status="done", out=out)
                        self.tree.set(iid, "status", f"✔ Done – {fmt_size(size)} ({saved:.0f}% smaller)")
                    self.log(f"  ✔ Saved {out}  ({fmt_size(size)})")
                elif kind == "step":
                    self.completed += 1
                    self.active.pop(m[1], None)
                    self._show_active()
                    self.cur_bar["value"] = (sum(self.active.values()) / len(self.active) * 1000) if self.active else 0
                    self.all_bar["value"] = self.completed / max(self.total, 1) * 1000
                elif kind == "log":
                    self.log(m[1])
                elif kind == "gpu":
                    self.gpu, self.gpu_checked = m[1], True
                    if self.gpu:
                        codecs = " + ".join(c for c, k in (("H.264", "h264"), ("H.265", "h265")) if self.gpu[k])
                        self.gpu_label.configure(text=f"GPU: {self.gpu['name']} found ({codecs})")
                        self.log(f"GPU encoder available: {self.gpu['name']} ({codecs})")
                    else:
                        self.gpu_label.configure(text="GPU: no supported GPU encoder found – the CPU will be used")
                    self._update_mode()
                elif kind == "lane_done":
                    self.ok_count += m[1]
                    self.lanes_left -= 1
                    if self.lanes_left > 0:
                        continue
                    ok, n = self.ok_count, self.total
                    cancelled = any(e.cancelled for e in self.encoders)
                    self.active = {}
                    self.cur_bar["value"] = 0
                    self._set_running(False)
                    self.status.configure(text=f"Finished: {ok} of {n} file(s) compressed."
                                          + ("  (cancelled)" if cancelled else ""))
                    self.log(f"=== Done: {ok}/{n} ===")
                    if ok and not cancelled:
                        self.bell()
                elif kind == "dl_progress":
                    _, done, total = m
                    pct = done * 100 / total if total else 0
                    self.status.configure(text=f"Downloading FFmpeg… {fmt_size(done)}"
                                          + (f" / {fmt_size(total)} ({pct:.0f}%)" if total else ""))
                    self.cur_bar["value"] = pct * 10
                elif kind == "dl_done":
                    self.cur_bar["value"] = 0
                    self.ffmpeg, self.ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
                    self.start_btn.configure(state="normal")
                    if self.ffmpeg and self.ffprobe:
                        self.status.configure(text="FFmpeg installed. Add videos to get started.")
                        self.log(f"FFmpeg installed to {tools_dir()}")
                        self._detect_gpu()
                    else:
                        self.status.configure(text="FFmpeg download failed.")
                elif kind == "update_info":
                    self._on_update_info(m[1], m[2])
                elif kind == "update_error":
                    _, msg, manual = m
                    self.update_btn.configure(state="normal")
                    if manual:
                        messagebox.showinfo(APP_NAME, msg)
                elif kind == "update_progress":
                    _, done, total = m
                    pct = done * 100 / total if total else 0
                    self.status.configure(text=f"Downloading update… {fmt_size(done)}"
                                          + (f" / {fmt_size(total)} ({pct:.0f}%)" if total else ""))
                    self.cur_bar["value"] = pct * 10
                elif kind == "update_ready":
                    self.status.configure(text="Update installed – restarting…")
                    self.update_idletasks()
                    try:
                        m[1]()
                    finally:
                        self.destroy()
                    return
                elif kind == "update_failed":
                    self.updating = False
                    self.cur_bar["value"] = 0
                    self.start_btn.configure(state="normal")
                    self.update_btn.configure(state="normal")
                    self.status.configure(text="Update failed.")
                    messagebox.showerror(APP_NAME, f"The update couldn't be installed:\n\n{m[1]}")
                elif kind == "dl_failed":
                    self.cur_bar["value"] = 0
                    self.start_btn.configure(state="normal")
                    self.status.configure(text="FFmpeg download failed.")
                    messagebox.showerror(APP_NAME, f"Could not download FFmpeg:\n{m[1]}\n\n"
                                         "You can install it manually – see README.")
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ---- updates -------------------------------------------------------
    def _check_updates(self, manual):
        if self.updating:
            return
        self.update_btn.configure(state="disabled")

        def run():
            try:
                self.msgs.put(("update_info", fetch_latest_release(), manual))
            except Exception as e:  # noqa: BLE001
                self.msgs.put(("update_error", str(e), manual))
        threading.Thread(target=run, daemon=True).start()

    def _on_update_info(self, rel, manual):
        self.update_btn.configure(state="normal")
        if parse_version(rel["version"]) <= parse_version(VERSION):
            if manual:
                messagebox.showinfo(APP_NAME, f"You're up to date (version {VERSION}).")
            return
        self.update_btn.configure(text=f"⬆ Update to v{rel['version']}")
        if self.worker:
            if manual:
                messagebox.showinfo(APP_NAME, f"Version {rel['version']} is available. Finish or cancel the "
                                              "current compression, then click the update button.")
            return
        notes = rel["notes"]
        if len(notes) > 900:
            notes = notes[:900].rsplit("\n", 1)[0] + "\n…"
        msg = (f"VidShrink {rel['version']} is available (you have {VERSION}).\n\n"
               + (f"What's new:\n{notes}\n\n" if notes else "")
               + "Install it now? VidShrink will restart.")
        if messagebox.askyesno(f"{APP_NAME} update", msg):
            self._start_update(rel)

    def _start_update(self, rel):
        self.updating = True
        self.start_btn.configure(state="disabled")
        self.update_btn.configure(state="disabled")
        self.log(f"Updating to {rel['version']}…")

        def run():
            try:
                finish = install_update(rel, lambda d, t: self.msgs.put(("update_progress", d, t)))
                self.msgs.put(("update_ready", finish))
            except Exception as e:  # noqa: BLE001
                self.msgs.put(("update_failed", str(e)))
        threading.Thread(target=run, daemon=True).start()

    # ---- FFmpeg setup --------------------------------------------------
    def _check_ffmpeg(self):
        if self.ffmpeg and self.ffprobe:
            self.log(f"Using FFmpeg: {self.ffmpeg}")
            self._detect_gpu()
            return
        if not IS_WIN:
            messagebox.showerror(APP_NAME, "FFmpeg was not found. Please install ffmpeg and ffprobe.")
            return
        if messagebox.askyesno(
                APP_NAME, "VidShrink uses the free FFmpeg engine to compress videos, "
                          "but it isn't installed yet.\n\nDownload it now? (about 100 MB, one time only)"):
            self.start_btn.configure(state="disabled")
            self.status.configure(text="Downloading FFmpeg…")

            def run():
                try:
                    download_ffmpeg(lambda d, t: self.msgs.put(("dl_progress", d, t)))
                    self.msgs.put(("dl_done",))
                except Exception as e:  # noqa: BLE001
                    self.msgs.put(("dl_failed", str(e)))
            threading.Thread(target=run, daemon=True).start()
        else:
            self.status.configure(text="FFmpeg is required. See README for manual install.")

    def _on_close(self):
        if self.worker and not messagebox.askyesno(APP_NAME, "A compression is running. Stop it and quit?"):
            return
        for enc in self.encoders:
            enc.cancel()
        self.destroy()


def main():
    if IS_WIN:
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
        if getattr(sys, "frozen", False):
            try:  # keep the version in Settings > Apps current after self-updates (set by install.ps1)
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VidShrink"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
            except OSError:
                pass
        try:  # show VidShrink's own icon in the taskbar instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.VideoCompressor")
        except Exception:  # noqa: BLE001
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
