#!/usr/bin/env python3
"""
VidShrink - a video compressor for Windows (a mini "Media Encoder").

Shrinks videos to a target size (e.g. 1 GB -> 500 MB) while keeping as much quality
as possible. This file is the Qt (PySide6) interface; vidshrink_core.py is the engine.

Requires: Python 3.9+, PySide6-Essentials (installed automatically on first run),
          FFmpeg (downloaded automatically on first run).
"""

import os
import queue
import subprocess
import sys
import threading
import time


def _ensure_pyside():
    """Source installs: install the Qt interface library on first run (or after an update)."""
    try:
        import PySide6  # noqa: F401
        return
    except ImportError:
        if getattr(sys, "frozen", False):
            raise
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    root = None
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        if not messagebox.askyesno(
                "VidShrink", "VidShrink's new interface needs the Qt library (a one-time download of "
                             "about 80 MB).\n\nInstall it now?"):
            sys.exit(1)
        note = tk.Toplevel(root)
        note.title("VidShrink")
        tk.Label(note, text="Installing the interface library…\nThis takes a minute.", padx=30,
                 pady=20).pack()
        note.update()
    except ImportError:
        print("Installing PySide6-Essentials…")
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "PySide6-Essentials"]
    ok = subprocess.run(cmd, creationflags=no_window).returncode == 0 or \
        subprocess.run(cmd + ["--user"], creationflags=no_window).returncode == 0
    if root is not None:
        root.destroy()
    if not ok:
        try:
            from tkinter import messagebox
            messagebox.showerror("VidShrink", "Couldn't install PySide6-Essentials. Run this in a terminal:\n\n"
                                              "python -m pip install PySide6-Essentials")
        except ImportError:
            pass
        sys.exit(1)
    subprocess.Popen([sys.executable] + sys.argv, close_fds=True)
    sys.exit(0)


_ensure_pyside()

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFont, QIcon, QImage, QKeySequence,  # noqa: E402
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,  # noqa: E402
                               QDialog, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QSpinBox, QStackedWidget, QTextBrowser, QVBoxLayout,
                               QWidget)

from vidshrink_core import (APP_NAME, IS_WIN, VERSION, VIDEO_EXTS, Cancelled, Encoder,  # noqa: E402
                            detect_gpu, download_ffmpeg, extract_thumbnail, fetch_latest_release, find_tool,
                            fmt_dur, fmt_size, install_update, parse_version, probe, resource_path,
                            target_bytes, tools_dir, update_download_size)

# ----------------------------------------------------------------------------
# Look (design A: "Studio")
# ----------------------------------------------------------------------------

C = {
    "bg": "#0B0D20", "panel": "#12152F", "list": "#10132C", "card": "#0F1230", "input": "#0B0D20",
    "line": "#22264A", "line2": "#2C3160", "track": "#1F2347", "text": "#E8EAF6", "muted": "#A3A8C8",
    "soft": "#C9CDE6", "accent": "#5E43E6", "accent_hi": "#6E55F0", "accent_lo": "#4F36D0",
    "sel": "#8C7BFF", "sel_bg": "#1B1C4A", "sel_sub": "#C3BCFF", "green": "#7EE2B8",
}
CHIPS = {  # status chip: (background, text, progress-bar colour)
    "cpu": ("#11384A", "#67E8F9", "#22D3EE"),
    "gpu": ("#4A1838", "#FF8CC6", "#F0459B"),
    "done": ("#123A2C", "#7EE2B8", "#34D399"),
    "fail": ("#4A1C24", "#FF9AA8", "#FB7185"),
    "wait": ("#1C2046", "#C9CDE6", "#1F2347"),
}
THUMB_TINTS = ("#2E3370", "#1D4E63", "#4B2D5C", "#3B4A2C", "#5A3A24", "#24485A")

QSS = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", Inter, sans-serif; font-size: 14px; color: {C['text']}; }}
QMainWindow, QWidget#root {{ background: {C['bg']}; }}
QWidget#header {{ border-bottom: 1px solid {C['line']}; }}
QWidget#footer {{ background: {C['card']}; border-top: 1px solid {C['line']}; }}
QScrollArea#side, QWidget#sideInner {{ background: {C['panel']}; border: 0; }}
QScrollArea#side {{ border-left: 1px solid {C['line']}; }}
QLabel {{ background: transparent; }}
QLabel[role="muted"] {{ color: {C['muted']}; font-size: 12px; }}
QLabel[role="soft"] {{ color: {C['soft']}; }}
QLabel[role="section"] {{ color: {C['muted']}; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; }}
QLabel[role="h1"] {{ font-size: 22px; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="pill"] {{ background: #1C2046; color: {C['soft']}; font-size: 12px; border-radius: 10px; padding: 2px 10px; }}
QPushButton {{ min-height: 38px; padding: 0 14px; border-radius: 8px; background: #161A3A;
               border: 1px solid {C['line2']}; }}
QPushButton:hover {{ background: #1D2148; }}
QPushButton:disabled {{ color: #5D6290; border-color: #23274D; }}
QPushButton[kind="primary"] {{ background: {C['accent']}; border: 0; font-weight: 600; color: #FFFFFF; }}
QPushButton[kind="primary"]:hover {{ background: {C['accent_hi']}; }}
QPushButton[kind="primary"]:pressed {{ background: {C['accent_lo']}; }}
QPushButton[kind="primary"]:disabled {{ background: #2C2A5E; color: #8E8BB8; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid #3A3F75; }}
QPushButton[kind="ghost"]:hover {{ background: #161A3A; }}
QPushButton[kind="small"] {{ min-height: 30px; padding: 0 12px; font-size: 13px; color: {C['soft']};
                             background: transparent; border: 1px solid {C['line2']}; border-radius: 6px; }}
QPushButton[kind="small"]:hover {{ background: #161A3A; }}
QPushButton[kind="update"] {{ min-height: 30px; padding: 0 12px; font-size: 13px; font-weight: 600; border-radius: 6px;
                              background: {C['accent']}; border: 0; color: #FFFFFF; }}
QWidget#seg {{ background: {C['input']}; border-radius: 8px; }}
QPushButton#segBtn {{ min-height: 34px; padding: 0 6px; background: transparent; border: 0; border-radius: 6px;
                      color: {C['soft']}; font-size: 13px; }}
QPushButton#segBtn:checked {{ background: #2A2F63; color: #FFFFFF; font-weight: 600; }}
QPushButton#card {{ min-height: 50px; padding: 0; text-align: left; background: {C['card']};
                    border: 1px solid {C['line2']}; border-radius: 8px; }}
QPushButton#card:hover {{ border-color: #3D4380; }}
QPushButton#card:checked {{ background: {C['sel_bg']}; border: 2px solid {C['sel']}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ min-height: 38px; padding: 0 10px; background: {C['input']};
    border: 1px solid {C['line2']}; border-radius: 8px; selection-background-color: {C['accent']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {C['sel']}; }}
QSpinBox QLineEdit, QDoubleSpinBox QLineEdit, QComboBox QLineEdit {{ min-height: 0; padding: 0; border: 0;
    background: transparent; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: #8E93B8;
    border-color: #23274D; }}
QSpinBox#big, QDoubleSpinBox#big {{ font-size: 16px; font-weight: 600; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: {C['panel']}; border: 1px solid {C['line2']};
    selection-background-color: #2A2F63; outline: 0; padding: 4px; }}
QSlider::groove:horizontal {{ height: 4px; background: {C['track']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C['sel']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: #FFFFFF; }}
QSlider::handle:horizontal:disabled {{ background: #5D6290; }}
QListWidget#queue {{ background: {C['list']}; border: 1px solid {C['line']}; border-radius: 12px; outline: 0;
                     padding: 0; }}
QListWidget#queue::item {{ border-bottom: 1px solid #1B1F42; }}
QListWidget#queue::item:selected {{ background: #1A1E46; }}
QListWidget#queue::item:hover {{ background: #141838; }}
QFrame#drop {{ border: 2px dashed {C['line2']}; border-radius: 12px; background: transparent; }}
QFrame#drop:hover {{ border-color: {C['sel']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2C3160; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: {C['panel']}; color: {C['text']}; border: 1px solid {C['line2']}; padding: 6px; }}
QMenu {{ background: {C['panel']}; border: 1px solid {C['line2']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: #2A2F63; }}
QMessageBox, QDialog#log {{ background: {C['panel']}; }}
QPlainTextEdit {{ background: {C['input']}; border: 1px solid {C['line2']}; border-radius: 8px;
                  font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }}
"""

UPDATE_QSS = f"""
QDialog#update {{ background: #FFFFFF; }}
QDialog#update * {{ font-family: "Segoe UI Variable Text", "Segoe UI", Inter, sans-serif; font-size: 14px;
                    color: #15172E; }}
QDialog#update QLabel {{ background: transparent; }}
QDialog#update QLabel#updTitle {{ font-size: 20px; font-weight: 700; }}
QDialog#update QLabel#updSub {{ color: #5B6078; }}
QDialog#update QLabel#updSection {{ color: #4A4F6A; font-size: 12px; font-weight: 700; letter-spacing: 0.5px; }}
QDialog#update QLabel#updSafe {{ color: #146B49; font-size: 12px; }}
QDialog#update QLabel#updError {{ color: #B42318; font-size: 12px; }}
QDialog#update QFrame#notesBox {{ background: #F6F7FB; border-radius: 10px; }}
QDialog#update QTextBrowser {{ background: transparent; border: 0; }}
QDialog#update QPushButton {{ min-height: 40px; padding: 0 20px; border-radius: 8px; background: #FFFFFF;
                              border: 1px solid #D9DCE8; }}
QDialog#update QPushButton:hover {{ background: #F4F5FA; }}
QDialog#update QPushButton:disabled {{ color: #9A9EB5; }}
QDialog#update QPushButton#updGo {{ background: {C['accent']}; border: 0; color: #FFFFFF; font-weight: 600; }}
QDialog#update QPushButton#updGo:hover {{ background: {C['accent_hi']}; }}
QDialog#update QPushButton#updGo:disabled {{ background: #B9B0F2; color: #FFFFFF; }}
QDialog#update QProgressBar {{ background: #E6E8F0; border: 0; border-radius: 4px; }}
QDialog#update QProgressBar::chunk {{ background: {C['accent']}; border-radius: 4px; }}
"""

# Labels shown in the UI -> engine values
MODES = (("Target size", "size"), ("Percent", "percent"), ("Quality", "quality"))
CODECS = (("H.264", "Plays everywhere", "h264"), ("H.265 / HEVC", "Best quality per MB", "h265"))
SPEEDS = (("Fast", "fast"), ("Balanced", "medium"), ("High", "slow"), ("Max", "slower"))
RESOLUTIONS = (("Keep original", 0), ("4K (2160p)", 2160), ("1440p", 1440), ("1080p", 1080),
               ("720p", 720), ("480p", 480))
AUDIO = ((64, "64 kbps"), (96, "96 kbps"), (128, "128 kbps"), (160, "160 kbps"), (192, "192 kbps"),
         (256, "256 kbps"))
ENGINES = (("Auto", "CPU encodes, GPU decodes · best quality", "auto"),
           ("GPU – fastest", "Often 5–10× faster, slightly lower quality", "gpu"),
           ("CPU only", "", "cpu"))


def crf_text(v):
    desc = ("visually lossless" if v <= 18 else "excellent" if v <= 21 else "great (default)" if v <= 24
            else "good, smaller" if v <= 27 else "small file")
    return f"{v} – {desc}"


# ----------------------------------------------------------------------------
# Small drawing helpers (icons are drawn, so no image files are needed)
# ----------------------------------------------------------------------------

def _icon_path(name):
    p = QPainterPath()

    def poly(*pts, close=False):
        p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        if close:
            p.closeSubpath()

    if name == "plus":
        poly((12, 5), (12, 19)); poly((5, 12), (19, 12))
    elif name == "folder":
        poly((3, 6), (9, 6), (11, 8), (21, 8), (21, 19), (3, 19), close=True)
    elif name == "refresh":
        p.arcMoveTo(QRectF(3, 3, 18, 18), 40)
        p.arcTo(QRectF(3, 3, 18, 18), 40, 290)
        poly((21, 3), (21, 9), (15, 9))
    elif name == "check":
        poly((5, 12), (10, 17), (20, 7))
    elif name == "upload":
        poly((12, 15), (12, 3)); poly((7, 8), (12, 3), (17, 8)); poly((4, 15), (4, 20), (20, 20), (20, 15))
    elif name == "shield":
        poly((12, 3), (20, 6), (20, 12), (12, 21), (4, 12), (4, 6), close=True)
        poly((8.5, 12), (11, 14.5), (15.5, 9.5))
    elif name == "log":
        poly((8, 6), (21, 6)); poly((8, 12), (21, 12)); poly((8, 18), (21, 18))
        poly((3, 6), (3.5, 6)); poly((3, 12), (3.5, 12)); poly((3, 18), (3.5, 18))
    elif name == "x":
        poly((6, 6), (18, 18)); poly((18, 6), (6, 18))
    return p


def make_icon(name, color="#FFFFFF", size=16, stroke=2.0):
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    col = QColor(color)
    if name in ("play", "pause"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        if name == "play":
            p.drawPolygon(QPolygonF([QPointF(7, 4), QPointF(20, 12), QPointF(7, 20)]))
        else:
            p.drawRoundedRect(QRectF(6, 5, 4, 14), 1, 1)
            p.drawRoundedRect(QRectF(14, 5, 4, 14), 1, 1)
    else:
        pen = QPen(col, stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_icon_path(name))
    p.end()
    return pm


def app_icon_pixmap():
    path = resource_path("icon.png")
    pm = QPixmap(path) if path else QPixmap()
    if pm.isNull():
        ico = resource_path("vidshrink.ico")
        if ico:
            pm = QIcon(ico).pixmap(256, 256)
    return pm


def thumb_pixmap(png, tint, w=84, h=48, r=6):
    dpr = 2
    pm = QPixmap(w * dpr, h * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.setClipPath(clip)
    img = QImage.fromData(png) if png else QImage()
    if not img.isNull():
        iw, ih = img.width(), img.height()
        if iw / ih > w / h:  # crop the sides
            cw = ih * w / h
            src = QRectF((iw - cw) / 2, 0, cw, ih)
        else:
            ch = iw * h / w
            src = QRectF(0, (ih - ch) / 2, iw, ch)
        p.drawImage(QRectF(0, 0, w, h), img, src)
    else:
        p.fillPath(clip, QColor(tint))
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor("#FFFFFF")
        c.setAlphaF(0.85)
        p.setBrush(c)
        cx, cy = w / 2, h / 2
        p.drawPolygon(QPolygonF([QPointF(cx - 5, cy - 7), QPointF(cx + 8, cy), QPointF(cx - 5, cy + 7)]))
    p.end()
    return pm


def set_role(w, role):
    w.setProperty("role", role)
    return w


def set_kind(w, kind):
    w.setProperty("kind", kind)
    return w


def label(text="", role=None, wrap=False):
    lb = QLabel(text)
    if role:
        set_role(lb, role)
    lb.setWordWrap(wrap)
    return lb


# ----------------------------------------------------------------------------
# Widgets
# ----------------------------------------------------------------------------

class ElideLabel(QLabel):
    """A one-line label that ends in "…" when it doesn't fit."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setFullText(text)

    def setFullText(self, text):
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(), 20)))


class ThinBar(QProgressBar):
    def __init__(self, height=4, color=None):
        super().__init__()
        self.setRange(0, 1000)
        self.setTextVisible(False)
        self.setFixedHeight(height)
        self._h = height
        self.set_color(color or C["accent"])

    def set_color(self, color):
        r = self._h // 2
        self.setStyleSheet(f"QProgressBar{{background:{C['track']};border:0;border-radius:{r}px}}"
                           f"QProgressBar::chunk{{background:{color};border-radius:{r}px}}")

    def set_fraction(self, f):
        self.setValue(int(max(0.0, min(1.0, f)) * 1000))


class Chip(QLabel):
    def set_chip(self, text, kind):
        bg, fg, _ = CHIPS[kind]
        self.setText(text)
        self.setStyleSheet(f"background:{bg};color:{fg};border-radius:11px;padding:3px 10px;"
                           f"font-size:12px;font-weight:600;")


class Switch(QCheckBox):
    """A toggle switch."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(44, 24)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        track = QColor(C["sel"] if on else "#2C3160")
        if not self.isEnabled():
            track.setAlphaF(0.45)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 1, 44, 22), 11, 11)
        p.setBrush(QColor("#FFFFFF" if self.isEnabled() else "#9AA0C8"))
        x = 24 if on else 4
        p.drawEllipse(QRectF(x, 4, 16, 16))
        p.end()


class RadioDot(QWidget):
    def __init__(self, button):
        super().__init__()
        self.button = button
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.button.isChecked()
        p.setPen(QPen(QColor(C["sel"] if on else "#5D6290"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(2, 2, 14, 14))
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["sel"]))
            p.drawEllipse(QRectF(5.5, 5.5, 7, 7))
        p.end()


class CardButton(QPushButton):
    """A checkable card with a bold title and a smaller line under it."""

    def __init__(self, title, sub="", radio=False):
        super().__init__()
        self.setObjectName("card")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        self.dot = RadioDot(self) if radio else None
        if self.dot:
            lay.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.t = QLabel(title)
        self.t.setStyleSheet("font-size:13px;font-weight:700;")
        col.addWidget(self.t)
        self.s = QLabel(sub)
        self.s.setVisible(bool(sub))
        col.addWidget(self.s)
        lay.addLayout(col, 1)
        for w in (self.t, self.s):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.toggled.connect(self._restyle)
        self._restyle(False)
        self.setAccessibleName(f"{title}. {sub}" if sub else title)

    def _restyle(self, on):
        self.s.setStyleSheet(f"font-size:12px;color:{C['sel_sub'] if on else C['muted']};")
        if self.dot:
            self.dot.update()

    def sizeHint(self):
        return QSize(120, 54 if self.s.isVisible() else 44)


class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, labels):
        super().__init__()
        self.setObjectName("seg")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        for i, text in enumerate(labels):
            b = QPushButton(text)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b, 1)
        self.group.idClicked.connect(self.changed.emit)

    def index(self):
        return self.group.checkedId()

    def set_index(self, i):
        self.group.button(i).setChecked(True)


class QueueRow(QWidget):
    """One video in the queue: thumbnail, name, details, progress, sizes and status."""

    def __init__(self, path, tint):
        super().__init__()
        self.tint = tint
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(16)
        self.thumb = QLabel()
        self.thumb.setFixedSize(84, 48)
        self.thumb.setPixmap(thumb_pixmap(None, tint))
        lay.addWidget(self.thumb)
        mid = QVBoxLayout()
        mid.setSpacing(4)
        self.name = ElideLabel(os.path.basename(path))
        self.name.setStyleSheet("font-weight:600;")
        mid.addWidget(self.name)
        self.meta = label("Reading…", "muted")
        mid.addWidget(self.meta)
        self.bar = ThinBar(4, CHIPS["wait"][2])
        mid.addWidget(self.bar)
        lay.addLayout(mid, 1)
        sizes = QVBoxLayout()
        sizes.setSpacing(2)
        self.sizes = QLabel("")
        self.note = label("", "muted")
        sizes.addWidget(self.sizes)
        sizes.addWidget(self.note)
        holder = QWidget()
        holder.setFixedWidth(170)
        holder.setLayout(sizes)
        sizes.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(holder)
        self.chip = Chip()
        chip_box = QWidget()
        chip_box.setFixedWidth(150)
        cb = QHBoxLayout(chip_box)
        cb.setContentsMargins(0, 0, 0, 0)
        self.chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        cb.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)
        cb.addStretch(1)
        lay.addWidget(chip_box)
        self.chip.set_chip("Reading…", "wait")

    def set_thumb(self, png):
        self.thumb.setPixmap(thumb_pixmap(png, self.tint))

    def set_status(self, text, kind, fraction=None):
        self.chip.set_chip(text, kind)
        self.bar.set_color(CHIPS[kind][2])
        if fraction is not None:
            self.bar.set_fraction(fraction)


class DropZone(QFrame):
    clicked = Signal()

    def __init__(self, text, big=False):
        super().__init__()
        self.setObjectName("drop")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self) if big else QHBoxLayout(self)
        lay.setContentsMargins(20, 18 if not big else 60, 20, 18 if not big else 60)
        lay.setSpacing(10)
        lay.addStretch(1)
        ic = QLabel()
        ic.setPixmap(make_icon("upload", C["muted"], 30 if big else 18))
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignCenter)
        t = QLabel(text)
        t.setStyleSheet(f"color:{C['muted']};" + ("font-size:16px;" if big else ""))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t, 0, Qt.AlignmentFlag.AlignCenter)
        if big:
            sub = label("Or click here to choose files. Any size, any length.", "muted")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(sub, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)
        self.setAccessibleName(text)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class Lane(QWidget):
    """CPU or GPU progress in the footer."""

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        tag = QLabel(kind.upper())
        bg, fg, bar = CHIPS[kind]
        tag.setStyleSheet(f"background:{bg};color:{fg};font-weight:700;font-size:12px;border-radius:4px;padding:1px 7px;")
        top.addWidget(tag)
        self.name = ElideLabel("")
        self.name.setStyleSheet(f"color:{C['soft']};font-size:12px;")
        top.addWidget(self.name, 1)
        self.pct = QLabel("")
        self.pct.setStyleSheet("font-size:12px;")
        top.addWidget(self.pct)
        v.addLayout(top)
        self.bar = ThinBar(4, bar)
        v.addWidget(self.bar)

    def show_job(self, name, f):
        self.name.setFullText(name)
        self.pct.setText(f"{f * 100:.0f}%")
        self.bar.set_fraction(f)


# ----------------------------------------------------------------------------
# Update dialog (design E)
# ----------------------------------------------------------------------------

class UpdateDialog(QDialog):
    update_requested = Signal()

    def __init__(self, parent, release):
        super().__init__(parent)
        self.setObjectName("update")
        self.setWindowTitle(f"{APP_NAME} update")
        self.setStyleSheet(UPDATE_QSS)
        self.setFixedWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 24)
        root.setSpacing(16)

        top = QHBoxLayout()
        top.setSpacing(16)
        icon = QLabel()
        pm = app_icon_pixmap()
        if not pm.isNull():
            icon.setPixmap(pm.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        icon.setFixedSize(56, 56)
        top.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title = QLabel(f"{APP_NAME} {release['version']} is available")
        self.title.setObjectName("updTitle")
        col.addWidget(self.title)
        size = update_download_size(release)
        self.sub = QLabel(f"You have {VERSION}" + (f" · {fmt_size(size)} download" if size else ""))
        self.sub.setObjectName("updSub")
        col.addWidget(self.sub)
        top.addLayout(col, 1)
        root.addLayout(top)

        box = QFrame()
        box.setObjectName("notesBox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(6)
        sec = QLabel("WHAT’S NEW")
        sec.setObjectName("updSection")
        bl.addWidget(sec)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(release.get("notes") or "Improvements and fixes.")
        self.notes.setFixedHeight(150)
        bl.addWidget(self.notes)
        root.addWidget(box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        root.addWidget(self.progress)

        safe = QHBoxLayout()
        safe.setSpacing(8)
        si = QLabel()
        si.setPixmap(make_icon("shield", "#146B49", 14, 2.2))
        safe.addWidget(si)
        self.safe = QLabel("Checked for tampering before it’s installed")
        self.safe.setObjectName("updSafe")
        safe.addWidget(self.safe, 1)
        root.addLayout(safe)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.later = QPushButton("Later")
        self.later.clicked.connect(self.reject)
        btns.addWidget(self.later)
        self.go = QPushButton("Update and restart")
        self.go.setObjectName("updGo")
        self.go.setDefault(True)
        self.go.clicked.connect(self._go)
        btns.addWidget(self.go)
        root.addLayout(btns)

    def _go(self):
        self.go.setEnabled(False)
        self.later.setEnabled(False)
        self.progress.show()
        self.title.setText(f"Downloading {APP_NAME}…")
        self.update_requested.emit()

    def set_progress(self, done, total):
        if total:
            self.progress.setValue(int(done * 1000 / total))
            self.sub.setText(f"{fmt_size(done)} of {fmt_size(total)}")
        else:
            self.sub.setText(f"{fmt_size(done)} downloaded")

    def set_installing(self):
        self.title.setText("Installing – VidShrink will restart")
        self.progress.setValue(1000)

    def set_failed(self, msg):
        self.title.setText("The update couldn’t be installed")
        self.safe.setObjectName("updError")
        self.safe.setText(msg)
        self.safe.setWordWrap(True)
        self.setStyleSheet(UPDATE_QSS)
        self.progress.hide()
        self.later.setText("Close")
        self.later.setEnabled(True)
        self.go.setText("Try again")
        self.go.setEnabled(True)


# ----------------------------------------------------------------------------
# Main window (design A)
# ----------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, startup_checks=True):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – Video Compressor")
        self.setAcceptDrops(True)
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)

        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        self.msgs = queue.Queue()
        self.jobs = {}          # id -> job dict
        self.next_id = 0
        self.worker = None      # truthy while compressing
        self.encoders = []
        self.gpu = None
        self.gpu_checked = False
        self.active = {}        # job id -> (fraction, lane)
        self.updating = False
        self.update_dialog = None
        self.paused = False
        self.total = self.completed = 0
        self.last_result = None  # (headline, detail) shown after a run
        self.dl_state = None     # (headline, detail, fraction) while FFmpeg downloads
        self.settings_store = QSettings(APP_NAME, APP_NAME)

        self._build()
        self._load_settings()
        self._refresh_mode()
        self._refresh_targets()
        self._refresh_count()
        self.cancel_btn.setEnabled(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(80)
        if startup_checks:
            QTimer.singleShot(400, self._check_ffmpeg)
            QTimer.singleShot(2500, lambda: self._check_updates(manual=False))

    # ---- layout --------------------------------------------------------
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_queue(), 1)
        body.addWidget(self._build_side())
        outer.addLayout(body, 1)
        outer.addWidget(self._build_footer())
        delete = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.list)
        delete.activated.connect(self._remove_selected)

    def _build_header(self):
        h = QWidget()
        h.setObjectName("header")
        h.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)
        icon = QLabel()
        pm = app_icon_pixmap()
        if not pm.isNull():
            small = pm.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            small.setDevicePixelRatio(2)
            icon.setPixmap(small)
        icon.setFixedSize(22, 22)
        lay.addWidget(icon)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-weight:600;")
        lay.addWidget(name)
        lay.addWidget(label(f"v{VERSION}", "muted"))
        lay.addStretch(1)
        self.log_btn = set_kind(QPushButton(" Log"), "small")
        self.log_btn.setIcon(QIcon(make_icon("log", C["soft"], 14)))
        self.log_btn.clicked.connect(self._show_log)
        lay.addWidget(self.log_btn)
        self.update_btn = set_kind(QPushButton(" Check for updates"), "small")
        self.update_btn.setIcon(QIcon(make_icon("refresh", C["soft"], 14)))
        self.update_btn.clicked.connect(lambda: self._check_updates(manual=True))
        lay.addWidget(self.update_btn)
        return h

    def _build_queue(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 24, 24, 20)
        v.setSpacing(16)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(label("Queue", "h1"))
        self.count_pill = label("", "pill")
        self.count_pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        top.addWidget(self.count_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        add = set_kind(QPushButton(" Add videos"), "primary")
        add.setIcon(QIcon(make_icon("plus", "#FFFFFF", 16, 2.4)))
        add.clicked.connect(self._add_files)
        add.setMinimumHeight(40)
        top.addWidget(add)
        addf = QPushButton(" Add folder")
        addf.setIcon(QIcon(make_icon("folder", C["text"], 16)))
        addf.clicked.connect(self._add_folder)
        addf.setMinimumHeight(40)
        top.addWidget(addf)
        self.add_buttons = (add, addf)
        v.addLayout(top)

        self.queue_stack = QStackedWidget()
        empty = DropZone("Drop videos here", big=True)
        empty.clicked.connect(self._add_files)
        self.queue_stack.addWidget(empty)

        page = QWidget()
        pv = QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)
        heads = QHBoxLayout()
        heads.setContentsMargins(17, 0, 17, 0)
        heads.setSpacing(16)
        sp = QWidget()
        sp.setFixedWidth(84)
        heads.addWidget(sp)
        heads.addWidget(label("File", "muted"), 1)
        for text, width in (("Size", 170), ("Status", 150)):
            lb = label(text, "muted")
            lb.setFixedWidth(width)
            heads.addWidget(lb)
        pv.addLayout(heads)
        self.list = QListWidget()
        self.list.setObjectName("queue")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._row_menu)
        self.list.itemDoubleClicked.connect(lambda it: self._reveal(it.data(Qt.ItemDataRole.UserRole)))
        pv.addWidget(self.list, 1)
        more = DropZone("Drop more videos here")
        more.clicked.connect(self._add_files)
        pv.addWidget(more)
        self.queue_stack.addWidget(page)
        v.addWidget(self.queue_stack, 1)
        return w

    def _build_side(self):
        scroll = QScrollArea()
        scroll.setObjectName("side")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(372)
        inner = QWidget()
        inner.setObjectName("sideInner")
        v = QVBoxLayout(inner)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(22)
        scroll.setWidget(inner)
        v.addWidget(label("Compression settings", "h2"))
        self.setting_widgets = []

        # Shrink to
        sec = QVBoxLayout()
        sec.setSpacing(10)
        sec.addWidget(label("SHRINK TO", "section"))
        self.mode_seg = Segmented([m[0] for m in MODES])
        self.mode_seg.changed.connect(lambda _: (self._refresh_mode(), self._refresh_targets()))
        sec.addWidget(self.mode_seg)
        self.value_stack = QStackedWidget()
        # size
        pg = QWidget()
        hl = QHBoxLayout(pg)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setObjectName("big")
        self.size_spin.setRange(0.1, 1e9)  # no upper limit in practice
        self.size_spin.setDecimals(1)
        self.size_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.size_spin.setValue(500)
        self.size_spin.setFixedWidth(120)
        self.size_spin.setAccessibleName("Target size")
        self.size_spin.valueChanged.connect(self._refresh_targets)
        hl.addWidget(self.size_spin)
        self.unit = QComboBox()
        self.unit.addItems(["MB", "GB"])
        self.unit.setFixedWidth(84)
        self.unit.setAccessibleName("Unit")
        self.unit.currentIndexChanged.connect(self._refresh_targets)
        hl.addWidget(self.unit)
        hl.addStretch(1)
        self.value_stack.addWidget(pg)
        # percent
        pg = QWidget()
        hl = QHBoxLayout(pg)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)
        self.pct_spin = QSpinBox()
        self.pct_spin.setObjectName("big")
        self.pct_spin.setRange(1, 99)
        self.pct_spin.setValue(50)
        self.pct_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.pct_spin.setFixedWidth(72)
        self.pct_spin.setAccessibleName("Percent of original")
        self.pct_spin.valueChanged.connect(self._refresh_targets)
        hl.addWidget(self.pct_spin)
        hl.addWidget(label("% of the original size", "soft"), 1)
        self.value_stack.addWidget(pg)
        # quality
        pg = QWidget()
        hl = QHBoxLayout(pg)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(12)
        self.crf = QSlider(Qt.Orientation.Horizontal)
        self.crf.setRange(16, 32)
        self.crf.setValue(23)
        self.crf.setAccessibleName("Quality level")
        hl.addWidget(self.crf, 1)
        self.crf_label = QLabel(crf_text(23))
        self.crf_label.setFixedWidth(150)
        self.crf.valueChanged.connect(lambda v: self.crf_label.setText(crf_text(v)))
        hl.addWidget(self.crf_label)
        self.value_stack.addWidget(pg)
        sec.addWidget(self.value_stack)
        v.addLayout(sec)

        # Codec
        sec = QVBoxLayout()
        sec.setSpacing(10)
        sec.addWidget(label("CODEC", "section"))
        grid = QHBoxLayout()
        grid.setSpacing(8)
        self.codec_group = QButtonGroup(self)
        for i, (title, sub, _) in enumerate(CODECS):
            b = CardButton(title, sub)
            self.codec_group.addButton(b, i)
            grid.addWidget(b, 1)
        sec.addLayout(grid)
        v.addLayout(sec)

        # Speed
        sec = QVBoxLayout()
        sec.setSpacing(8)
        sec.addWidget(label("SPEED VS QUALITY", "section"))
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, len(SPEEDS) - 1)
        self.speed.setPageStep(1)
        self.speed.setValue(1)
        self.speed.setAccessibleName("Speed versus quality")
        sec.addWidget(self.speed)
        ticks = QHBoxLayout()
        self.speed_labels = []
        for i, (text, _) in enumerate(SPEEDS):
            lb = QLabel(text)
            lb.setAlignment(Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight
                            if i == len(SPEEDS) - 1 else Qt.AlignmentFlag.AlignCenter)
            ticks.addWidget(lb, 1)
            self.speed_labels.append(lb)
        sec.addLayout(ticks)
        self.speed.valueChanged.connect(self._refresh_speed_labels)
        v.addLayout(sec)

        # Resolution + audio
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.addWidget(label("RESOLUTION", "section"), 0, 0)
        grid.addWidget(label("AUDIO", "section"), 0, 1)
        self.res = QComboBox()
        for text, val in RESOLUTIONS:
            self.res.addItem(text, val)
        self.res.setAccessibleName("Resolution")
        grid.addWidget(self.res, 1, 0)
        self.audio = QComboBox()
        for val, text in AUDIO:
            self.audio.addItem(text, val)
        self.audio.setCurrentIndex(2)
        self.audio.setAccessibleName("Audio bitrate")
        grid.addWidget(self.audio, 1, 1)
        v.addLayout(grid)

        # Encoder
        sec = QVBoxLayout()
        sec.setSpacing(8)
        sec.addWidget(label("ENCODER", "section"))
        self.engine_group = QButtonGroup(self)
        for i, (title, sub, _) in enumerate(ENGINES):
            b = CardButton(title, sub, radio=True)
            self.engine_group.addButton(b, i)
            sec.addWidget(b)
        gl = QHBoxLayout()
        gl.setSpacing(8)
        self.gpu_icon = QLabel()
        gl.addWidget(self.gpu_icon)
        self.gpu_label = QLabel("Checking for a graphics card…")
        self.gpu_label.setWordWrap(True)
        self.gpu_label.setStyleSheet(f"font-size:12px;color:{C['muted']};")
        gl.addWidget(self.gpu_label, 1)
        sec.addLayout(gl)
        v.addLayout(sec)

        # Fast batch
        fb = QHBoxLayout()
        fb.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel("Fast batch")
        t.setStyleSheet("font-size:13px;font-weight:700;")
        col.addWidget(t)
        col.addWidget(label("CPU and GPU each work on a file at once", "muted", wrap=True))
        fb.addLayout(col, 1)
        self.fast_batch = Switch()
        self.fast_batch.setAccessibleName("Fast batch")
        self.fast_batch.setEnabled(False)  # until a GPU is found
        fb.addWidget(self.fast_batch)
        v.addLayout(fb)

        # Save to
        sec = QVBoxLayout()
        sec.setSpacing(6)
        sec.addWidget(label("SAVE TO", "section"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.outdir = QLineEdit()
        self.outdir.setPlaceholderText("Next to the original")
        self.outdir.setClearButtonEnabled(True)
        self.outdir.setAccessibleName("Save to folder")
        row.addWidget(self.outdir, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._pick_outdir)
        row.addWidget(browse)
        sec.addLayout(row)
        v.addLayout(sec)
        v.addStretch(1)

        self.setting_widgets = [self.mode_seg, self.value_stack, *self.codec_group.buttons(), self.speed,
                                self.res, self.audio, *self.engine_group.buttons(), self.fast_batch,
                                self.outdir, browse]
        return scroll

    def _build_footer(self):
        f = QWidget()
        f.setObjectName("footer")
        f.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(24, 14, 24, 14)
        lay.setSpacing(24)
        overall = QVBoxLayout()
        overall.setSpacing(6)
        top = QHBoxLayout()
        self.overall_label = QLabel("")
        self.overall_label.setStyleSheet("font-weight:700;font-size:13px;")
        top.addWidget(self.overall_label)
        top.addStretch(1)
        self.eta_label = label("", "muted")
        top.addWidget(self.eta_label)
        overall.addLayout(top)
        self.overall_bar = ThinBar(8, C["accent"])
        overall.addWidget(self.overall_bar)
        ow = QWidget()
        ow.setLayout(overall)
        overall.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(ow, 3)
        self.lanes = {"cpu": Lane("cpu"), "gpu": Lane("gpu")}
        for lane in self.lanes.values():
            lane.hide()
            lay.addWidget(lane, 2)
        self.cancel_btn = set_kind(QPushButton("Cancel"), "ghost")
        self.cancel_btn.setMinimumHeight(44)
        self.cancel_btn.clicked.connect(self._cancel)
        lay.addWidget(self.cancel_btn)
        self.start_btn = set_kind(QPushButton(" Start"), "primary")
        self.start_btn.setMinimumHeight(44)
        self.start_btn.setMinimumWidth(130)
        self.start_btn.clicked.connect(self._primary_clicked)
        lay.addWidget(self.start_btn)
        return f

    # ---- settings ------------------------------------------------------
    def settings(self):
        size = self.size_spin.value() * (1024 if self.unit.currentIndex() == 1 else 1)
        return {
            "mode": MODES[max(self.mode_seg.index(), 0)][1],
            "size_mb": size,
            "percent": float(self.pct_spin.value()),
            "crf": self.crf.value(),
            "codec": CODECS[max(self.codec_group.checkedId(), 0)][2],
            "preset": SPEEDS[self.speed.value()][1],
            "height": self.res.currentData(),
            "audio_kbps": self.audio.currentData(),
            "engine": ENGINES[max(self.engine_group.checkedId(), 0)][2],
            "fast_batch": self.fast_batch.isChecked(),
            "gpu": self.gpu,
        }

    def _load_settings(self):
        st = self.settings_store

        def get(key, default, typ=str):
            try:
                v = st.value(key, default)
                return typ(v) if v is not None else default
            except (TypeError, ValueError):
                return default
        self.mode_seg.set_index(min(get("mode", 0, int), 2))
        self.size_spin.setValue(get("size", 500.0, float))
        self.unit.setCurrentIndex(min(get("unit", 0, int), 1))
        self.pct_spin.setValue(get("percent", 50, int))
        self.crf.setValue(get("crf", 23, int))
        self.codec_group.button(min(get("codec", 0, int), 1)).setChecked(True)
        self.speed.setValue(get("speed", 1, int))
        self.res.setCurrentIndex(min(get("res", 0, int), self.res.count() - 1))
        self.audio.setCurrentIndex(min(get("audio", 2, int), self.audio.count() - 1))
        self.engine_group.button(min(get("engine", 0, int), 2)).setChecked(True)
        self.fast_batch.setChecked(get("fast_batch", "false", str).lower() == "true")
        self.outdir.setText(get("outdir", "", str))
        geo = st.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._refresh_speed_labels(self.speed.value())

    def _save_settings(self):
        st = self.settings_store
        st.setValue("mode", self.mode_seg.index())
        st.setValue("size", self.size_spin.value())
        st.setValue("unit", self.unit.currentIndex())
        st.setValue("percent", self.pct_spin.value())
        st.setValue("crf", self.crf.value())
        st.setValue("codec", self.codec_group.checkedId())
        st.setValue("speed", self.speed.value())
        st.setValue("res", self.res.currentIndex())
        st.setValue("audio", self.audio.currentIndex())
        st.setValue("engine", self.engine_group.checkedId())
        st.setValue("fast_batch", "true" if self.fast_batch.isChecked() else "false")
        st.setValue("outdir", self.outdir.text().strip())
        st.setValue("geometry", self.saveGeometry())

    def _refresh_mode(self):
        self.value_stack.setCurrentIndex(max(self.mode_seg.index(), 0))

    def _refresh_speed_labels(self, value):
        for i, lb in enumerate(self.speed_labels):
            lb.setStyleSheet("font-size:12px;" + ("color:#FFFFFF;font-weight:700;" if i == value
                                                   else f"color:{C['muted']};"))

    def _target_texts(self, info):
        s = self.settings()
        t = target_bytes(info, s)
        if t is None:
            return f"{fmt_size(info['size'])} → ?", "quality mode"
        if t >= info["size"]:
            return f"{fmt_size(info['size'])}", "already smaller"
        note = f"target {s['percent']:.0f}%" if s["mode"] == "percent" else "target size"
        return f"{fmt_size(info['size'])} → {fmt_size(t)}", note

    def _refresh_targets(self, *_):
        for j in self.jobs.values():
            if j["info"] and j["status"] in ("ready", "failed", "cancelled", "skipped"):
                sizes, note = self._target_texts(j["info"])
                j["row"].sizes.setText(sizes)
                j["row"].note.setText(note)

    # ---- queue ---------------------------------------------------------
    def log(self, text):
        self.log_view.appendPlainText(text)

    @property
    def log_view(self):
        if not hasattr(self, "_log_view"):
            self._log_view = QPlainTextEdit()
            self._log_view.setReadOnly(True)
            self._log_view.setMaximumBlockCount(5000)
        return self._log_view

    def _show_log(self):
        if not hasattr(self, "_log_dialog"):
            d = QDialog(self)
            d.setObjectName("log")
            d.setWindowTitle(f"{APP_NAME} – Log")
            d.resize(760, 460)
            lay = QVBoxLayout(d)
            lay.addWidget(self.log_view)
            row = QHBoxLayout()
            row.addStretch(1)
            copy = QPushButton("Copy all")
            copy.clicked.connect(lambda: QApplication.clipboard().setText(self.log_view.toPlainText()))
            row.addWidget(copy)
            close = set_kind(QPushButton("Close"), "primary")
            close.clicked.connect(d.close)
            row.addWidget(close)
            lay.addLayout(row)
            self._log_dialog = d
        self._log_dialog.show()
        self._log_dialog.raise_()

    def _add_files(self):
        if self.worker:
            return
        exts = " ".join("*" + e for e in VIDEO_EXTS)
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose videos to compress", "",
                                                f"Video files ({exts});;All files (*.*)")
        self._add_paths(paths)

    def _add_folder(self):
        if self.worker:
            return
        d = QFileDialog.getExistingDirectory(self, "Choose a folder of videos")
        if d:
            paths = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(VIDEO_EXTS)]
            if not paths:
                QMessageBox.information(self, APP_NAME, "No video files found in that folder.")
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
            if p in existing or not os.path.isfile(p):
                continue
            jid = self.next_id
            self.next_id += 1
            row = QueueRow(p, THUMB_TINTS[jid % len(THUMB_TINTS)])
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, jid)
            item.setSizeHint(QSize(100, 74))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self.last_result = None
            self.jobs[jid] = {"path": p, "info": None, "status": "reading", "out": None, "row": row,
                              "item": item, "error": ""}
            threading.Thread(target=self._probe_worker, args=(jid, p), daemon=True).start()
        self._refresh_count()

    def _probe_worker(self, jid, path):
        try:
            info = probe(self.ffprobe, path)
            self.msgs.put(("probed", jid, info))
            self.msgs.put(("thumb", jid, extract_thumbnail(self.ffmpeg, path, info["duration"])))
        except Exception as e:  # noqa: BLE001
            self.msgs.put(("probe_failed", jid, str(e)))

    def _refresh_count(self):
        n = len(self.jobs)
        total = sum(j["info"]["size"] for j in self.jobs.values() if j["info"])
        self.count_pill.setText(f"{n} video{'s' if n != 1 else ''}" + (f" · {fmt_size(total)}" if total else ""))
        self.count_pill.setVisible(n > 0)
        self.queue_stack.setCurrentIndex(1 if n else 0)
        self._refresh_footer()

    def _remove_selected(self):
        if self.worker:
            return
        for item in self.list.selectedItems():
            jid = item.data(Qt.ItemDataRole.UserRole)
            self.list.takeItem(self.list.row(item))
            self.jobs.pop(jid, None)
        self._refresh_count()

    def _row_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        jid = item.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        show = QAction("Show in Explorer", m)
        show.triggered.connect(lambda: self._reveal(jid))
        m.addAction(show)
        j = self.jobs.get(jid)
        if j and j["error"]:
            err = QAction("Why did this fail?", m)
            err.triggered.connect(lambda: QMessageBox.information(self, APP_NAME, j["error"]))
            m.addAction(err)
        if not self.worker:
            rm = QAction("Remove from queue", m)
            rm.triggered.connect(self._remove_selected)
            m.addAction(rm)
        m.exec(self.list.viewport().mapToGlobal(pos))

    def _reveal(self, jid):
        j = self.jobs.get(jid)
        path = j and (j["out"] or j["path"])
        if not path or not os.path.exists(path):
            return
        if IS_WIN:
            subprocess.Popen(["explorer", "/select,", path])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "Save compressed videos to…")
        if d:
            self.outdir.setText(os.path.normpath(d))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and not self.worker:
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                paths += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(VIDEO_EXTS)]
            elif p:
                paths.append(p)
        self._add_paths(paths)

    # ---- running -------------------------------------------------------
    def _validate(self, s):
        if s["mode"] == "size" and s["size_mb"] <= 0:
            return "Please enter a target size (e.g. 500 MB)."
        out = self.outdir.text().strip()
        if out and not os.path.isdir(out):
            return f"The folder to save to doesn't exist:\n{out}"
        return None

    def _primary_clicked(self):
        if not self.worker:
            self._start()
        elif self.paused:
            self._resume()
        else:
            self._pause()

    def _start(self):
        if not self.ffmpeg:
            self._check_ffmpeg()
            return
        if self.updating:
            return
        s = self.settings()
        err = self._validate(s)
        if err:
            QMessageBox.warning(self, APP_NAME, err)
            return
        todo = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        todo = [jid for jid in todo if self.jobs[jid]["info"]
                and self.jobs[jid]["status"] in ("ready", "failed", "cancelled")]
        if not todo:
            QMessageBox.information(self, APP_NAME, "Nothing to do – add some videos first.")
            return
        self.total, self.completed = len(todo), 0
        self.active = {}
        self.ok_count = 0
        self.last_result = None
        self.paused = False
        self.run_started = time.monotonic()
        self.paused_total = 0.0
        outdir = self.outdir.text().strip()

        gpu_ok = bool(s["gpu"] and s["gpu"].get(s["codec"]))
        if s["fast_batch"] and gpu_ok and len(todo) > 1:
            lanes = [("cpu", "[CPU] "), ("gpu", "[GPU] ")]
        elif s["engine"] == "gpu":
            lanes = [("gpu", "")]
        else:
            lanes = [("cpu", "")]
        if s["fast_batch"] and not gpu_ok:
            self.log("Fast batch needs a supported GPU for this codec – running on the CPU only.")
        for jid in todo:
            j = self.jobs[jid]
            j["status"] = "waiting"
            j["error"] = ""
            j["row"].set_status("Waiting", "wait", 0)
            sizes, note = self._target_texts(j["info"])
            j["row"].sizes.setText(sizes)
            j["row"].note.setText(note)

        jobs = queue.Queue()
        for jid in todo:
            jobs.put(jid)
        self.encoders = []
        self.lanes_left = len(lanes)
        self.worker = True
        self._set_running(True)
        self.log(f"=== Starting {len(todo)} file(s)" + (" – CPU and GPU in parallel" if len(lanes) > 1 else "") + " ===")
        for engine, tag in lanes:
            enc = Encoder(self.ffmpeg, lambda t, tag=tag: self.msgs.put(("log", tag + t)))
            self.encoders.append(enc)
            threading.Thread(target=self._work, args=(enc, engine, tag, jobs, s, outdir), daemon=True).start()
        self._refresh_footer()

    def _work(self, enc, engine, tag, jobs, s, outdir):
        ok = 0
        hwdecode = s["engine"] != "cpu"
        while not enc.cancelled:
            try:
                jid = jobs.get_nowait()
            except queue.Empty:
                break
            j = self.jobs.get(jid)
            if not j:
                continue
            # the GPU lane can still fall back to the CPU inside the engine; the badge shows the lane
            lane = "gpu" if engine == "gpu" else "cpu"
            self.msgs.put(("running", jid, lane))
            self.msgs.put(("log", f"{tag}▶ {os.path.basename(j['path'])}  ({fmt_size(j['info']['size'])}, "
                                  f"{fmt_dur(j['info']['duration'])})"))
            try:
                out, size = enc.encode(j["path"], j["info"], s, outdir,
                                       lambda f, jid=jid, lane=lane: self.msgs.put(("progress", jid, f, lane)),
                                       engine=engine, hwdecode=hwdecode)
                self.msgs.put(("finished", jid, out, size))
                ok += 1
            except Cancelled:
                self.msgs.put(("ended", jid, "cancelled", "Cancelled"))
                self.msgs.put(("log", f"{tag}  Cancelled."))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                state = "skipped" if "skipped" in msg else "failed"
                self.msgs.put(("ended", jid, state, msg))
                self.msgs.put(("log", f"{tag}  ✖ {msg}"))
            self.msgs.put(("step", jid))
        self.msgs.put(("lane_done", ok))

    def _pause(self):
        self.paused = True
        self.pause_started = time.monotonic()
        for enc in self.encoders:
            enc.pause()
        self.log("Paused.")
        self._refresh_footer()

    def _resume(self):
        self.paused = False
        self.paused_total += time.monotonic() - self.pause_started
        for enc in self.encoders:
            enc.resume()
        self.log("Resumed.")
        self._refresh_footer()

    def _cancel(self):
        if not self.worker:
            return
        for enc in self.encoders:
            enc.cancel()
        self.paused = False
        self.overall_label.setText("Cancelling…")

    def _set_running(self, running):
        for w in self.setting_widgets + list(self.add_buttons):
            w.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        if not running:
            self.worker = None
            self._refresh_gpu_controls()

    def _refresh_footer(self):
        running = bool(self.worker)
        if running:
            frac = (self.completed + sum(f for f, _ in self.active.values())) / max(self.total, 1)
            self.overall_label.setText(f"Overall · {frac * 100:.0f}%")
            self.overall_bar.set_fraction(frac)
            done_txt = f"{self.completed} of {self.total} done"
            if self.paused:
                self.eta_label.setText(f"{done_txt} · paused")
            else:
                elapsed = time.monotonic() - self.run_started - self.paused_total
                if frac > 0.02 and elapsed > 3:
                    left = elapsed * (1 - frac) / frac
                    eta = "less than a minute left" if left < 60 else f"about {left / 60:.0f} min left"
                    self.eta_label.setText(f"{done_txt} · {eta}")
                else:
                    self.eta_label.setText(f"{done_txt} · estimating time…")
            self.start_btn.setText(" Resume" if self.paused else " Pause")
            self.start_btn.setIcon(QIcon(make_icon("play" if self.paused else "pause", "#FFFFFF", 14)))
        else:
            n = sum(1 for j in self.jobs.values() if j["status"] in ("ready", "failed", "cancelled"))
            if self.dl_state:
                head, detail, frac = self.dl_state
            elif self.last_result:
                (head, detail), frac = self.last_result, 1.0
            else:
                head = "Ready" if n else "Add videos to get started"
                detail = f"{n} video{'s' if n != 1 else ''} to compress" if n else ""
                frac = 0
            self.overall_label.setText(head)
            self.eta_label.setText(detail)
            self.overall_bar.set_fraction(frac)
            self.start_btn.setText(" Start")
            self.start_btn.setIcon(QIcon(make_icon("play", "#FFFFFF", 14)))
            self.start_btn.setEnabled(bool(n) and not self.updating)
            for lane in self.lanes.values():
                lane.hide()
        for kind, lane in self.lanes.items():
            jobs_here = [(jid, f) for jid, (f, k) in self.active.items() if k == kind]
            if running and jobs_here:
                jid, f = jobs_here[0]
                lane.show_job(os.path.basename(self.jobs[jid]["path"]), f)
                lane.show()

    def _poll(self):
        changed = False
        try:
            while True:
                m = self.msgs.get_nowait()
                kind = m[0]
                changed = True
                if kind == "probed":
                    _, jid, info = m
                    j = self.jobs.get(jid)
                    if j:
                        j.update(info=info, status="ready")
                        j["row"].meta.setText(f"{fmt_dur(info['duration'])} · {info['width']}×{info['height']} · "
                                              f"{info['vcodec'].upper()}")
                        j["row"].set_status("Ready", "wait", 0)
                        self._refresh_targets()
                        self._refresh_count()
                elif kind == "thumb":
                    _, jid, png = m
                    if jid in self.jobs and png:
                        self.jobs[jid]["row"].set_thumb(png)
                elif kind == "probe_failed":
                    _, jid, err = m
                    j = self.jobs.get(jid)
                    if j:
                        j.update(status="invalid", error=err)
                        j["row"].meta.setText("Can't read this file")
                        j["row"].set_status("Can't read", "fail", 0)
                        self.log(f"✖ {os.path.basename(j['path'])}: {err}")
                elif kind == "running":
                    _, jid, lane = m
                    if jid in self.jobs:
                        self.jobs[jid]["status"] = "running"
                        self.active[jid] = (0.0, lane)
                        self.jobs[jid]["row"].set_status(f"{lane.upper()} · 0%", lane, 0)
                        self.list.scrollToItem(self.jobs[jid]["item"])
                elif kind == "progress":
                    _, jid, f, lane = m
                    if jid in self.active:
                        self.active[jid] = (f, lane)
                        self.jobs[jid]["row"].set_status(f"{lane.upper()} · {f * 100:.0f}%", lane, f)
                elif kind == "finished":
                    _, jid, out, size = m
                    j = self.jobs.get(jid)
                    if j:
                        saved = 100 - size * 100.0 / j["info"]["size"]
                        j.update(status="done", out=out)
                        j["row"].set_status("Done", "done", 1)
                        j["row"].sizes.setText(f"{fmt_size(j['info']['size'])} → {fmt_size(size)}")
                        j["row"].note.setText(f"{saved:.0f}% smaller")
                        self.log(f"  ✔ Saved {out}  ({fmt_size(size)})")
                elif kind == "ended":
                    _, jid, state, msg = m
                    j = self.jobs.get(jid)
                    if j:
                        j.update(status=state, error="" if state == "cancelled" else msg)
                        text = {"cancelled": "Cancelled", "skipped": "Skipped", "failed": "Failed"}[state]
                        j["row"].set_status(text, "wait" if state != "failed" else "fail", 0)
                        j["row"].setToolTip(msg if state != "cancelled" else "")
                        if state == "skipped":
                            j["row"].note.setText("already smaller")
                elif kind == "step":
                    self.completed += 1
                    self.active.pop(m[1], None)
                elif kind == "log":
                    self.log(m[1])
                elif kind == "gpu":
                    self.gpu, self.gpu_checked = m[1], True
                    if self.gpu:
                        codecs = " + ".join(c for c, k in (("H.264", "h264"), ("H.265", "h265")) if self.gpu[k])
                        self.log(f"GPU encoder available: {self.gpu['name']} ({codecs})")
                    self._refresh_gpu_controls()
                elif kind == "lane_done":
                    self.ok_count += m[1]
                    self.lanes_left -= 1
                    if self.lanes_left == 0:
                        self._finish_run()
                elif kind == "dl_progress":
                    _, done, total = m
                    self.dl_state = ("Downloading FFmpeg…", fmt_size(done) + (f" of {fmt_size(total)}" if total else ""),
                                     done / total if total else 0)
                elif kind == "dl_done":
                    self.dl_state = None
                    self.ffmpeg, self.ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
                    if self.ffmpeg and self.ffprobe:
                        self.log(f"FFmpeg installed to {tools_dir()}")
                        self._detect_gpu()
                elif kind == "dl_failed":
                    self.dl_state = None
                    QMessageBox.critical(self, APP_NAME, f"Couldn't download FFmpeg:\n{m[1]}\n\n"
                                                         "You can install it yourself – see the README.")
                elif kind == "update_info":
                    self._on_update_info(m[1], m[2])
                elif kind == "update_error":
                    _, msg, manual = m
                    self.update_btn.setEnabled(True)
                    if manual:
                        QMessageBox.information(self, APP_NAME, msg)
                elif kind == "update_progress":
                    if self.update_dialog:
                        self.update_dialog.set_progress(m[1], m[2])
                elif kind == "update_ready":
                    if self.update_dialog:
                        self.update_dialog.set_installing()
                    QApplication.processEvents()
                    self._save_settings()
                    try:
                        m[1]()
                    finally:
                        QApplication.quit()
                    return
                elif kind == "update_failed":
                    self.updating = False
                    self.update_btn.setEnabled(True)
                    if self.update_dialog:
                        self.update_dialog.set_failed(m[1])
                    else:
                        QMessageBox.critical(self, APP_NAME, f"The update couldn't be installed:\n\n{m[1]}")
        except queue.Empty:
            pass
        if changed or (self.worker and not self.paused):
            self._refresh_footer()

    def _finish_run(self):
        ok, n = self.ok_count, self.total
        cancelled = any(e.cancelled for e in self.encoders)
        self.active = {}
        self.paused = False
        self._set_running(False)
        for j in self.jobs.values():
            if j["status"] == "waiting":
                j["status"] = "ready"
                j["row"].set_status("Ready", "wait", 0)
        saved = sum(j["info"]["size"] - os.path.getsize(j["out"]) for j in self.jobs.values()
                    if j["status"] == "done" and j["out"] and os.path.exists(j["out"]))
        self.last_result = (f"Finished: {ok} of {n} compressed" + (" (cancelled)" if cancelled else ""),
                            f"Saved {fmt_size(saved)} in total" if saved > 0 else "")
        self._refresh_footer()
        self.log(f"=== Done: {ok}/{n} ===")
        if ok and not cancelled:
            QApplication.beep()

    # ---- GPU -------------------------------------------------------------
    def _detect_gpu(self):
        if not self.ffmpeg or self.gpu_checked:
            return
        threading.Thread(target=lambda: self.msgs.put(("gpu", detect_gpu(self.ffmpeg))), daemon=True).start()

    def _refresh_gpu_controls(self):
        if not self.gpu_checked:
            return
        if self.gpu:
            codecs = " + ".join(c for c, k in (("H.264", "h264"), ("H.265", "h265")) if self.gpu[k])
            self.gpu_label.setText(f"{self.gpu['name']} found · {codecs}")
            self.gpu_label.setStyleSheet(f"font-size:12px;color:{C['green']};")
            self.gpu_icon.setPixmap(make_icon("check", C["green"], 14, 2.4))
        else:
            self.gpu_label.setText("No supported graphics card found – the CPU will be used")
            self.gpu_label.setStyleSheet(f"font-size:12px;color:{C['muted']};")
            self.gpu_icon.clear()
        if not self.worker:
            self.fast_batch.setEnabled(bool(self.gpu))

    # ---- updates -------------------------------------------------------
    def _check_updates(self, manual):
        if self.updating:
            return
        self.update_btn.setEnabled(False)

        def run():
            try:
                self.msgs.put(("update_info", fetch_latest_release(), manual))
            except Exception as e:  # noqa: BLE001
                self.msgs.put(("update_error", str(e), manual))
        threading.Thread(target=run, daemon=True).start()

    def _on_update_info(self, rel, manual):
        self.update_btn.setEnabled(True)
        if parse_version(rel["version"]) <= parse_version(VERSION):
            if manual:
                QMessageBox.information(self, APP_NAME, f"You're up to date (version {VERSION}).")
            return
        set_kind(self.update_btn, "update")
        self.update_btn.setText(f" Update to v{rel['version']}")
        self.update_btn.setIcon(QIcon(make_icon("refresh", "#FFFFFF", 14)))
        self.update_btn.style().unpolish(self.update_btn)
        self.update_btn.style().polish(self.update_btn)
        if self.worker:
            if manual:
                QMessageBox.information(self, APP_NAME, f"Version {rel['version']} is available. Finish or cancel "
                                                        "the current compression, then click the update button.")
            return
        self.show_update_dialog(rel)

    def show_update_dialog(self, rel):
        self.update_dialog = UpdateDialog(self, rel)
        self.update_dialog.update_requested.connect(lambda: self._start_update(rel))
        self.update_dialog.finished.connect(lambda _: setattr(self, "update_dialog", None)
                                            if not self.updating else None)
        self.update_dialog.open()

    def _start_update(self, rel):
        self.updating = True
        self.start_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self.log(f"Updating to {rel['version']}…")

        def run():
            try:
                finish = install_update(rel, lambda d, t: self.msgs.put(("update_progress", d, t)))
                self.msgs.put(("update_ready", finish))
            except Exception as e:  # noqa: BLE001
                self.msgs.put(("update_failed", str(e)))
        threading.Thread(target=run, daemon=True).start()

    # ---- FFmpeg ----------------------------------------------------------
    def _check_ffmpeg(self):
        if self.ffmpeg and self.ffprobe:
            if not self.gpu_checked:
                self.log(f"Using FFmpeg: {self.ffmpeg}")
            self._detect_gpu()
            return
        if not IS_WIN:
            QMessageBox.critical(self, APP_NAME, "FFmpeg was not found. Please install ffmpeg and ffprobe.")
            return
        if QMessageBox.question(self, APP_NAME, "VidShrink uses the free FFmpeg engine to compress videos, but it "
                                                "isn't installed yet.\n\nDownload it now? (about 100 MB, one time "
                                                "only)") != QMessageBox.StandardButton.Yes:
            self.overall_label.setText("FFmpeg is needed – see the README to install it yourself")
            return

        def run():
            try:
                download_ffmpeg(lambda d, t: self.msgs.put(("dl_progress", d, t)))
                self.msgs.put(("dl_done",))
            except Exception as e:  # noqa: BLE001
                self.msgs.put(("dl_failed", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def closeEvent(self, e):
        if self.worker and QMessageBox.question(
                self, APP_NAME, "A compression is running. Stop it and quit?") != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        for enc in self.encoders:
            enc.cancel()
        self._save_settings()
        e.accept()


def dark_title_bar(window):
    """Windows 10/11: make the title bar match the dark app."""
    if not IS_WIN:
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                break
        color = ctypes.c_int(0x00200D0B)  # DWMWA_CAPTION_COLOR, 0x00BBGGRR for #0B0D20 (Windows 11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)
    except Exception:  # noqa: BLE001
        pass


def windows_setup():
    if not IS_WIN:
        return
    try:  # own taskbar icon instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.VideoCompressor")
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


def create_app(argv=None):
    windows_setup()
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    ico = resource_path("vidshrink.ico")
    if ico:
        app.setWindowIcon(QIcon(ico))
    else:
        pm = app_icon_pixmap()
        if not pm.isNull():
            app.setWindowIcon(QIcon(pm))
    f = QFont("Segoe UI Variable Text" if IS_WIN else "Inter")
    f.setPixelSize(14)
    app.setFont(f)
    return app


def main():
    selftest = "--selftest" in sys.argv  # used by the release build: start, draw, quit
    app = create_app()
    win = MainWindow(startup_checks=not selftest)
    win.show()
    dark_title_bar(win)
    if selftest:
        QTimer.singleShot(2500, lambda: app.exit(0 if win.isVisible() else 3))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
