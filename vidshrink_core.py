"""
VidShrink engine: probing, two-pass / GPU encoding, FFmpeg setup and self-updates.

No user interface here; vidshrink.py is the Qt app that drives it.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import hashlib
import urllib.error
import urllib.request
import zipfile


APP_NAME = "VidShrink"
VERSION = "1.1.0"  # bump this and push to main to publish an update to all users
GITHUB_REPO = "unknownleaves/vidshrink"  # updates are published as GitHub Releases here
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # hide console windows on Windows
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

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
        "sizes": {a["name"]: a.get("size", 0) for a in data.get("assets", [])},
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


def update_download_size(release):
    """Bytes this install will download for the given release."""
    name = EXE_ASSET if getattr(sys, "frozen", False) else SOURCE_ASSET
    return release.get("sizes", {}).get(name, 0)


def extract_thumbnail(ffmpeg, path, duration, width=168):
    """PNG bytes of one frame from about 10% into the video, or None."""
    t = max(0.0, min(duration * 0.1, duration - 0.5))
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
             "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2pipe", "-c:v", "png", "-"],
            capture_output=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=30)
        return r.stdout if r.returncode == 0 and r.stdout else None
    except (OSError, subprocess.SubprocessError):
        return None


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
        self.paused = False

    def _suspend(self, pause):
        """Freeze or unfreeze the running FFmpeg process."""
        p = self.proc
        if not p or p.poll() is not None:
            return
        try:
            if IS_WIN:
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x0800, False, p.pid)  # PROCESS_SUSPEND_RESUME
                if handle:
                    try:
                        fn = ctypes.windll.ntdll.NtSuspendProcess if pause else ctypes.windll.ntdll.NtResumeProcess
                        fn(handle)
                    finally:
                        ctypes.windll.kernel32.CloseHandle(handle)
            else:
                import signal
                os.kill(p.pid, signal.SIGSTOP if pause else signal.SIGCONT)
        except (OSError, AttributeError):
            pass

    def pause(self):
        self.paused = True
        self._suspend(True)

    def resume(self):
        self.paused = False
        self._suspend(False)

    def cancel(self):
        self.cancelled = True
        if self.paused:
            self.resume()
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
        if self.paused:  # a new pass started while paused
            self._suspend(True)
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
