"""GUI smoke test, run on Windows by GitHub Actions before every release.

Drives the real Qt window: adds videos, runs a parallel CPU+GPU batch (with pause and
resume), a GPU-mode H.265 batch and a cancelled batch, and checks the results.
Saves screenshots to $SCREENSHOT_DIR. Failures become GitHub "::error::" annotations.
"""
import glob
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vidshrink_core as core  # noqa: E402
import vidshrink as ui  # noqa: E402
from PySide6.QtCore import QSettings, QTimer  # noqa: E402

TIMEOUT = 900
SHOTS = os.environ.get("SCREENSHOT_DIR")
win = None


def fail(msg):
    if win is not None:
        print("----- app log -----")
        print(win.log_view.toPlainText())
        shot("failure")
    print(f"::error::{msg}")
    sys.stdout.flush()
    os._exit(1)  # exit for real, even from inside a Qt callback


def shot(name, widget=None):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        (widget or win).grab().save(os.path.join(SHOTS, f"{name}.png"))
        print(f"  screenshot {name}.png")


class AutoBox:
    """Stands in for QMessageBox so no dialog blocks the test."""
    StandardButton = ui.QMessageBox.StandardButton

    @staticmethod
    def question(*a, **k):
        print("dialog (question):", a[1:3])
        return ui.QMessageBox.StandardButton.No

    @staticmethod
    def _show(*a, **k):
        print("dialog:", a[1:3])

    information = warning = critical = _show


ui.QMessageBox = AutoBox

if not core.find_tool("ffmpeg"):
    print("Downloading FFmpeg…")
    core.download_ffmpeg(lambda d, t: None)
ff = core.find_tool("ffmpeg")
if not ff or not core.find_tool("ffprobe"):
    fail("FFmpeg could not be set up")

work = tempfile.mkdtemp(prefix="vidshrink_ci_")
out_dir = os.path.join(work, "out")
os.makedirs(out_dir)
srcs = []
for name, src in (("Wedding_Highlights.mp4", "testsrc2"), ("Drone_Coast.mp4", "mandelbrot"),
                  ("Zoom_Recording.mp4", "smptehdbars")):
    p = os.path.join(work, name)
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"{src}=size=1280x720:rate=30",
                    "-f", "lavfi", "-i", "sine=f=440", "-t", "12", "-vf", "noise=alls=6:allf=t",
                    "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast",
                    "-c:a", "aac", "-b:a", "192k", p], check=True)
    srcs.append(p)

QSettings(core.APP_NAME, core.APP_NAME).clear()
app = ui.create_app([])
win = ui.MainWindow(startup_checks=False)
win.resize(1280, 820)
win.show()
ui.dark_title_bar(win)
win._check_ffmpeg()  # finds FFmpeg, starts GPU detection
st = {"phase": "wait_gpu", "t0": time.time(), "t_phase": time.time()}


def phase(name):
    print(f"--- {name} ({time.time() - st['t0']:.0f}s)")
    st["phase"], st["t_phase"] = name, time.time()


def since():
    return time.time() - st["t_phase"]


def reset_jobs():
    for j in win.jobs.values():
        j["status"] = "ready"


def check_done(label, max_ratio=None):
    for j in win.jobs.values():
        if j["status"] != "done" or not j["out"] or not os.path.isfile(j["out"]):
            fail(f"{label}: {os.path.basename(j['path'])} ended as '{j['status']}' {j['error']}")
        size = os.path.getsize(j["out"])
        if max_ratio and size > j["info"]["size"] * max_ratio:
            fail(f"{label}: output {size} bytes is over target ({max_ratio:.0%} of {j['info']['size']})")
        print(f"  ok {os.path.basename(j['out'])}: {core.fmt_size(size)}")


def step():
    if time.time() - st["t0"] > TIMEOUT:
        fail(f"Timed out in phase '{st['phase']}'")
    ph = st["phase"]
    try:
        if ph == "wait_gpu" and win.gpu_checked:
            print("Detected GPU:", win.gpu)
            shot("1-empty")
            win._add_paths(srcs)
            phase("wait_probe")
        elif ph == "wait_probe" and len(win.jobs) == 3 and all(j["status"] == "ready" for j in win.jobs.values()) \
                and since() > 2:
            # Fake GPU: the GPU lane must fall back to the CPU by itself while the CPU lane runs alongside
            win.gpu = {"vendor": "nvidia", "name": "NVIDIA (NVENC)", "h264": "h264_nvenc", "h265": "hevc_nvenc"}
            win._refresh_gpu_controls()
            win.mode_seg.set_index(1)
            win._refresh_mode()
            win.pct_spin.setValue(30)
            win.codec_group.button(1).setChecked(True)
            win.speed.setValue(2)
            win.fast_batch.setChecked(True)
            win._refresh_targets()
            shot("2-queue-ready")
            win.speed.setValue(1)
            win.codec_group.button(0).setChecked(True)
            win.outdir.setText(out_dir)
            win._start()
            phase("batch1")
        elif ph == "batch1" and win.worker and not st.get("paused") and \
                sum(1 for f, _ in win.active.values() if f > 0.15) >= 2:
            shot("3-running")
            win._pause()
            st["paused"] = time.time()
            st["frozen"] = {k: v[0] for k, v in win.active.items()}
        elif ph == "batch1" and st.get("paused") and not st.get("resumed") and time.time() - st["paused"] > 2:
            now = {k: v[0] for k, v in win.active.items()}
            moved = [k for k in now if k in st["frozen"] and now[k] > st["frozen"][k] + 0.05]
            if moved:
                fail(f"Pause didn't stop encoding (progress moved: {st['frozen']} -> {now})")
            if "paused" not in win.eta_label.text():
                fail(f"Footer doesn't say paused: {win.eta_label.text()!r}")
            if win.start_btn.text().strip() != "Resume":
                fail(f"Primary button should say Resume, says {win.start_btn.text()!r}")
            shot("4-paused")
            win._resume()
            st["resumed"] = True
        elif ph == "batch1" and not win.worker:
            if not st.get("resumed"):
                fail("Batch finished before pause/resume could be tested")
            check_done("Fast batch", max_ratio=0.30 * 1.03)
            log = win.log_view.toPlainText()
            if "[GPU]" not in log or "[CPU]" not in log:
                fail("Fast batch did not run CPU and GPU lanes in parallel")
            if "using the CPU instead" not in log:
                fail("GPU lane did not fall back to the CPU")
            if "Finished: 3 of 3" not in win.overall_label.text():
                fail(f"Footer should report the finished batch: {win.overall_label.text()!r}")
            shot("5-finished")
            reset_jobs()
            win.fast_batch.setChecked(False)
            win.engine_group.button(1).setChecked(True)
            win.codec_group.button(1).setChecked(True)
            win.mode_seg.set_index(2)
            win._refresh_mode()
            win._start()
            phase("batch2")
        elif ph == "batch2" and not win.worker:
            check_done("GPU-mode H.265 batch")
            reset_jobs()
            win.engine_group.button(0).setChecked(True)
            win.codec_group.button(0).setChecked(True)
            win.mode_seg.set_index(0)
            win._refresh_mode()
            win.size_spin.setValue(1)
            win.speed.setValue(3)
            win._start()
            phase("batch3")
        elif ph == "batch3" and win.worker and since() > 2 and not st.get("cancelled"):
            st["cancelled"] = True
            win._cancel()
        elif ph == "batch3" and not win.worker:
            states = [j["status"] for j in win.jobs.values()]
            if "cancelled" not in states:
                fail(f"Cancel did not stop the batch (states: {states})")
            leftovers = glob.glob(os.path.join(out_dir, "*.partial.mp4"))
            if leftovers:
                fail(f"Cancel left partial files behind: {leftovers}")
            print("  ok cancel:", states)
            # Update dialog (design E), with placeholder notes for the screenshot only
            rel = {"version": "9.9.0", "tag": "v9.9.0", "url": "", "assets": {},
                   "sizes": {core.EXE_ASSET: 47_000_000, core.SOURCE_ASSET: 210_000},
                   "notes": "- Example release note one\n- Example release note two\n- Example release note three"}
            win.show_update_dialog(rel)
            phase("dialog")
        elif ph == "dialog" and since() > 1:
            shot("6-update-dialog", win.update_dialog)
            from PySide6.QtWidgets import QScrollArea
            shot("7-settings-panel", win.findChild(QScrollArea, "side").widget())
            win.update_dialog.reject()
            phase("done")
            print("ALL GUI SMOKE TESTS PASSED")
            print(f"::notice::Qt GUI smoke test passed in {time.time() - st['t0']:.0f}s: parallel CPU+GPU batch "
                  "with pause/resume (GPU fell back to CPU), GPU-mode H.265 batch, cancel, update dialog. "
                  f"GPU on runner: {core.detect_gpu(ff)}")
            app.quit()
            return
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        fail(f"Exception in phase '{ph}': {e!r}")
    QTimer.singleShot(200, step)


QTimer.singleShot(500, step)
app.exec()
if st["phase"] != "done":
    fail(f"Window closed early in phase '{st['phase']}'")
