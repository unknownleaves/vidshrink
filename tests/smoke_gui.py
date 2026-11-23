"""GUI smoke test, run on Windows by GitHub Actions before every release.

Drives the real VidShrink window: adds videos, runs a parallel CPU+GPU batch,
a GPU-mode H.265 batch and a cancelled batch, and checks the results.
Failures are reported as GitHub "::error::" annotations.
"""
import glob
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vidshrink as v  # noqa: E402

TIMEOUT = 900


def fail(msg, app=None):
    if app is not None:
        print("----- app log -----")
        print(app.logbox.get("1.0", "end"))
    print(f"::error::{msg}")
    sys.exit(1)


# Never block on a dialog in CI
v.messagebox.askyesno = lambda *a, **k: False
for name in ("showinfo", "showwarning", "showerror"):
    setattr(v.messagebox, name, lambda *a, **k: print("dialog:", a))

if not v.find_tool("ffmpeg"):
    print("Downloading FFmpeg…")
    v.download_ffmpeg(lambda d, t: None)
ff = v.find_tool("ffmpeg")
if not ff or not v.find_tool("ffprobe"):
    fail("FFmpeg could not be set up")

work = tempfile.mkdtemp(prefix="vidshrink_ci_")
out_dir = os.path.join(work, "out")
os.makedirs(out_dir)
srcs = []
for i in range(3):
    p = os.path.join(work, f"clip{i}.mp4")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30,noise=alls=6:allf=t",
                    "-f", "lavfi", "-i", "sine=f=440", "-t", "6",
                    "-c:v", "libx264", "-crf", "12", "-preset", "ultrafast",
                    "-c:a", "aac", "-b:a", "192k", p], check=True)
    srcs.append(p)

app = v.App()
st = {"phase": "wait_gpu", "t0": time.time(), "t_phase": time.time()}


def phase(name):
    print(f"--- {name} ({time.time() - st['t0']:.0f}s)")
    st["phase"], st["t_phase"] = name, time.time()


def reset_jobs():
    for j in app.jobs.values():
        j["status"] = "ready"


def check_done(label, max_ratio=None):
    for iid, j in app.jobs.items():
        if j["status"] != "done" or not j["out"] or not os.path.isfile(j["out"]):
            fail(f"{label}: {os.path.basename(j['path'])} ended as '{j['status']}'", app)
        size = os.path.getsize(j["out"])
        if max_ratio and size > j["info"]["size"] * max_ratio:
            fail(f"{label}: output {size} bytes is over target ({max_ratio:.0%} of {j['info']['size']})", app)
        print(f"  ok {os.path.basename(j['out'])}: {v.fmt_size(size)}")


def step():
    if time.time() - st["t0"] > TIMEOUT:
        fail(f"Timed out in phase '{st['phase']}'", app)
    ph = st["phase"]
    try:
        if ph == "wait_gpu" and app.gpu_checked:
            print("Detected GPU:", app.gpu)
            app._add_paths(srcs)
            phase("wait_probe")
        elif ph == "wait_probe" and len(app.jobs) == 3 and all(j["status"] == "ready" for j in app.jobs.values()):
            # 1) Fast batch, size target. CI has no GPU, so use a fake one: the GPU lane must
            #    fall back to the CPU by itself while the CPU lane runs in parallel.
            app.gpu = {"vendor": "nvidia", "name": "CI fake GPU", "h264": "h264_nvenc", "h265": "hevc_nvenc"}
            app.mode.set("percent")
            app.percent.set("30")
            app.fast_batch.set(True)
            app.preset.set("Fast")
            app.outdir.set(out_dir)
            app._start()
            phase("batch1")
        elif ph == "batch1" and not app.worker:
            check_done("Fast batch", max_ratio=0.30 * 1.03)
            log = app.logbox.get("1.0", "end")
            if "[GPU]" not in log or "[CPU]" not in log:
                fail("Fast batch did not run CPU and GPU lanes in parallel", app)
            if "using the CPU instead" not in log:
                fail("GPU lane did not fall back to the CPU", app)
            # 2) GPU mode + H.265 + constant quality
            reset_jobs()
            app.fast_batch.set(False)
            app.engine.set(list(v.ENGINES)[1])
            app.codec.set(list(v.CODECS)[1])
            app.mode.set("quality")
            app._start()
            phase("batch2")
        elif ph == "batch2" and not app.worker:
            check_done("GPU-mode H.265 batch")
            # 3) Cancel part-way through a slow encode
            reset_jobs()
            app.engine.set(list(v.ENGINES)[0])
            app.codec.set(list(v.CODECS)[0])
            app.mode.set("size")
            app.size_mb.set("1")
            app.preset.set("Maximum quality (very slow)")
            app._start()
            phase("batch3")
        elif ph == "batch3" and app.worker and time.time() - st["t_phase"] > 2 and not st.get("cancelled"):
            st["cancelled"] = True
            app._cancel()
        elif ph == "batch3" and not app.worker:
            states = [j["status"] for j in app.jobs.values()]
            if "cancelled" not in states:
                fail(f"Cancel did not stop the batch (states: {states})", app)
            leftovers = glob.glob(os.path.join(out_dir, "*.partial.mp4"))
            if leftovers:
                fail(f"Cancel left partial files behind: {leftovers}", app)
            print("  ok cancel:", states)
            phase("done")
            print("ALL GUI SMOKE TESTS PASSED")
            print(f"::notice::GUI smoke test passed in {time.time() - st['t0']:.0f}s: parallel CPU+GPU batch "
                  f"(GPU fell back to CPU), GPU-mode H.265 batch, cancel. Detected GPU on runner: "
                  f"{v.detect_gpu(ff)}")
            app.destroy()
            return
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        fail(f"Exception in phase '{ph}': {e!r}", app)
    app.after(250, step)


app.after(500, step)
app.mainloop()
if st["phase"] != "done":
    fail(f"Window closed early in phase '{st['phase']}'")
