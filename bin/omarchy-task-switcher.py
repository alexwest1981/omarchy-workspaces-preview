#!/usr/bin/env python3
# ==============================================================================
# Omarchy Visual Task Switcher & Window Preview HUD 🖥️✨
# Hybrid macOS / Window-Preview Switcher for Omarchy / Hyprland
#
# Part of the Omarchy Workspaces Preview Plugin
# https://github.com/alexwest1981/omarchy-workspaces-preview
# ==============================================================================

import sys
import os
import json
import subprocess
import glob
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QThread, pyqtSlot, QSize, QRectF
from PyQt6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter, QPainterPath,
    QKeyEvent, QMouseEvent, QCursor, QBrush, QPen, QLinearGradient
)

# ------------------------------------------------------------------------------
# 1. Hyprland IPC & Client Parsing
# ------------------------------------------------------------------------------
def run_hyprctl(command_args):
    try:
        res = subprocess.run(["hyprctl", "-j"] + command_args, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except Exception as e:
        print(f"[Switcher] Hyprctl error: {e}", file=sys.stderr)
        return []

def get_hyprland_data():
    clients = run_hyprctl(["clients"])
    monitors = run_hyprctl(["monitors"])
    workspaces = run_hyprctl(["workspaces"])
    
    # Active / focused monitor
    focused_mon = None
    mon_map = {}
    active_ws_across_monitors = set()
    for m in monitors:
        mon_map[m.get("id")] = m.get("description") or m.get("model") or m.get("name") or "Screen"
        if m.get("focused"):
            focused_mon = m
        active_ws_info = m.get("activeWorkspace", {})
        if active_ws_info and "id" in active_ws_info:
            active_ws_across_monitors.add(active_ws_info["id"])
            
    if not focused_mon and monitors:
        focused_mon = monitors[0]

    # Find occupied workspace IDs
    occupied_ws = set()
    for ws in workspaces:
        occupied_ws.add(ws.get("id"))

    # Next free workspace
    next_free_ws = 1
    for i in range(1, 11):
        if i not in occupied_ws:
            next_free_ws = i
            break
    else:
        next_free_ws = max(occupied_ws, default=1) + 1

    # Filter and sort windows by focusHistoryID (MRU order)
    valid_windows = []
    for c in clients:
        ws_info = c.get("workspace", {})
        ws_id = ws_info.get("id", 0)
        title = (c.get("title") or "").strip()
        app_cls = (c.get("class") or "").strip()
        init_cls = (c.get("initialClass") or "").strip()
        
        if not title and not app_cls:
            continue
        if ws_id < 0:  # Ignore special scratchpads if hidden
            continue
        if "omarchy-task-switcher" in app_cls or "omarchy-workspaces-picker" in title:
            continue
            
        at = c.get("at", [0, 0])
        sz = c.get("size", [0, 0])
        
        valid_windows.append({
            "address": c.get("address"),
            "title": title or "Untitled Window",
            "class": app_cls or init_cls or "Application",
            "initialClass": init_cls,
            "workspace": ws_id,
            "workspace_name": ws_info.get("name", str(ws_id)),
            "monitor_id": c.get("monitor"),
            "monitor_name": mon_map.get(c.get("monitor"), "Screen"),
            "pid": c.get("pid", 0),
            "floating": c.get("floating", False),
            "focus_history": c.get("focusHistoryID", 999),
            "at": at,
            "size": sz,
            "is_visible": ws_id in active_ws_across_monitors and sz[0] > 0 and sz[1] > 0
        })

    valid_windows.sort(key=lambda w: w["focus_history"])
    return valid_windows, focused_mon, next_free_ws


# ------------------------------------------------------------------------------
# 2. High-Quality Icon & App Name Resolver
# ------------------------------------------------------------------------------
class IconResolver:
    _desktop_map = {}
    _icon_paths = {}
    _pixmap_cache = {}
    _initialized = False

    @classmethod
    def _strip_known_ext(cls, name):
        for ext in ('.png', '.svg', '.xpm', '.ico', '.desktop'):
            if name.lower().endswith(ext):
                return name[:-len(ext)]
        return name

    @classmethod
    def initialize(cls):
        if cls._initialized:
            return
        cls._initialized = True

        dirs = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications")
        ]
        for d in dirs:
            if os.path.isdir(d):
                for fp in glob.glob(os.path.join(d, "*.desktop")):
                    try:
                        icon, wm, name, exec_cmd = "", "", "", ""
                        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("Icon=") and not icon:
                                    icon = line.split("=", 1)[1].strip()
                                elif line.startswith("StartupWMClass=") and not wm:
                                    wm = line.split("=", 1)[1].strip()
                                elif line.startswith("Name=") and not name:
                                    name = line.split("=", 1)[1].strip()
                                elif line.startswith("Exec=") and not exec_cmd:
                                    exec_cmd = line.split("=", 1)[1].split()[0].strip()
                        
                        base = cls._strip_known_ext(os.path.basename(fp)).lower()
                        entry = (icon, name)
                        if base:
                            cls._desktop_map[base] = entry
                        if wm:
                            cls._desktop_map[wm.lower()] = entry
                        if exec_cmd:
                            cls._desktop_map[os.path.basename(exec_cmd).lower()] = entry
                    except Exception:
                        pass

        icon_roots = [
            "/usr/share/icons/hicolor",
            "/usr/share/icons",
            "/usr/share/pixmaps",
            os.path.expanduser("~/.local/share/icons"),
            os.path.expanduser("~/.icons")
        ]
        for root in icon_roots:
            if not os.path.isdir(root):
                continue
            for r, _, files in os.walk(root):
                for f in files:
                    if f.endswith((".png", ".svg", ".xpm", ".ico")):
                        name_no_ext = cls._strip_known_ext(f).lower()
                        full_path = os.path.join(r, f)
                        
                        score = 10
                        if "256x256" in full_path:
                            score = 60
                        elif "128x128" in full_path:
                            score = 50
                        elif "512x512" in full_path or "1024x1024" in full_path:
                            score = 45
                        elif "scalable" in full_path:
                            score = 40
                        elif "64x64" in full_path:
                            score = 30
                        elif "48x48" in full_path:
                            score = 20

                        if name_no_ext not in cls._icon_paths or score > cls._icon_paths[name_no_ext][1]:
                            cls._icon_paths[name_no_ext] = (full_path, score)

    @classmethod
    def resolve(cls, app_class, initial_class="", title=""):
        cls.initialize()
        key = (app_class or initial_class or "").lower()
        if key in cls._pixmap_cache:
            return cls._pixmap_cache[key]

        candidates = [key]
        display_name = app_class or "Application"

        for search_k in [key, (initial_class or "").lower()]:
            if search_k in cls._desktop_map:
                icon_val, d_name = cls._desktop_map[search_k]
                if icon_val:
                    candidates.insert(0, icon_val)
                if d_name:
                    display_name = d_name

        if "discord" in key:
            candidates.extend(["omarchy-discord", "discord", "com.discordapp.Discord"])
            display_name = "Discord"
        elif "brave" in key:
            candidates.extend(["brave-desktop", "brave-browser", "brave"])
            display_name = "Brave Browser"
        elif "ghostty" in key:
            candidates.extend(["com.mitchellh.ghostty", "ghostty"])
            display_name = "Ghostty"
        elif "alacritty" in key:
            candidates.extend(["Alacritty", "alacritty"])
            display_name = "Alacritty"
        elif "code" in key or "vscode" in key:
            candidates.extend(["visual-studio-code", "code", "vscode"])
            display_name = "Visual Studio Code"
        elif "cursor" in key:
            candidates.extend(["cursor", "code"])
            display_name = "Cursor"
        elif "omascribe" in key:
            candidates.extend(["omascribe"])
            display_name = "OmaScribe"
        elif "obsidian" in key:
            candidates.extend(["obsidian", "md.obsidian.Obsidian"])
            display_name = "Obsidian"
        elif "spotify" in key:
            candidates.extend(["spotify", "spotify-client"])
            display_name = "Spotify"
        elif "nautilus" in key or "files" in key:
            candidates.extend(["org.gnome.Nautilus", "system-file-manager", "nautilus"])
            display_name = "Files"

        for c in candidates:
            if not c:
                continue
            if os.path.isabs(c) and os.path.exists(c):
                pix = QPixmap(c)
                if not pix.isNull():
                    cls._pixmap_cache[key] = (pix, display_name)
                    return pix, display_name

            c_clean = cls._strip_known_ext(os.path.basename(c)).lower()
            if c_clean in cls._icon_paths:
                icon_file = cls._icon_paths[c_clean][0]
                pix = QPixmap(icon_file)
                if not pix.isNull():
                    cls._pixmap_cache[key] = (pix, display_name)
                    return pix, display_name

        for c in candidates:
            if not c:
                continue
            ic = QIcon.fromTheme(c)
            if not ic.isNull():
                pix = ic.pixmap(128, 128)
                if not pix.isNull():
                    cls._pixmap_cache[key] = (pix, display_name)
                    return pix, display_name

        pix = cls._generate_fallback_badge(display_name or key)
        cls._pixmap_cache[key] = (pix, display_name)
        return pix, display_name

    @classmethod
    def _generate_fallback_badge(cls, text):
        pix = QPixmap(96, 96)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(4, 4, 88, 88, 20, 20)
        painter.fillPath(path, QColor("#1e293b"))
        painter.setPen(QColor("#60a5fa"))
        painter.drawPath(path)

        char_label = (text[:2] if len(text) >= 2 else text[:1]).upper() if text else "🪟"
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        painter.drawText(0, 0, 96, 96, Qt.AlignmentFlag.AlignCenter, char_label)
        painter.end()
        return pix


# ------------------------------------------------------------------------------
# 3. Async Live Window Thumbnail Capturer
# ------------------------------------------------------------------------------
class ThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(str, str)  # address, filepath

    def __init__(self, windows):
        super().__init__()
        self.windows = windows
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        for w in self.windows:
            if not self._running:
                break
            if not w.get("is_visible"):
                continue
            addr = w["address"]
            x, y = w["at"]
            width, height = w["size"]
            if width <= 10 or height <= 10:
                continue
            out_file = f"/tmp/hypr_thumb_{addr}.png"
            try:
                res = subprocess.run(
                    ["grim", "-g", f"{x},{y} {width}x{height}", out_file],
                    capture_output=True,
                    check=False
                )
                if res.returncode == 0 and os.path.exists(out_file) and self._running:
                    self.thumbnail_ready.emit(addr, out_file)
            except Exception:
                pass


# ------------------------------------------------------------------------------
# 4. Modern Window Preview Card Widget
# ------------------------------------------------------------------------------
class WindowPreviewCard(QFrame):
    clicked = pyqtSignal(int)

    CARD_WIDTH = 208
    CARD_HEIGHT = 136

    def __init__(self, index, window_info, parent=None):
        super().__init__(parent)
        self.index = index
        self.win = window_info
        self.is_selected = False
        self.thumbnail_pixmap = None

        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        # Resolve icon
        self.icon_pix, self.display_name = IconResolver.resolve(
            self.win["class"], 
            self.win.get("initialClass", ""), 
            self.win["title"]
        )
        self.win["display_name"] = self.display_name

        # Check existing thumbnail
        cached_file = f"/tmp/hypr_thumb_{self.win['address']}.png"
        if os.path.exists(cached_file):
            self.set_thumbnail_file(cached_file)

        self.update()

    def set_thumbnail_file(self, filepath):
        pix = QPixmap(filepath)
        if not pix.isNull():
            self.thumbnail_pixmap = pix
            self.update()

    def set_selected(self, selected: bool):
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        radius = 12.0
        rect = QRectF(2, 2, w - 4, h - 4)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)

        # 1. Background Fill / Thumbnail
        painter.save()
        painter.setClipPath(clip_path)

        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            scaled = self.thumbnail_pixmap.scaled(
                int(rect.width()), int(rect.height()),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # Center crop
            sx = (scaled.width() - int(rect.width())) // 2
            sy = (scaled.height() - int(rect.height())) // 2
            painter.drawPixmap(int(rect.x()), int(rect.y()), scaled, sx, sy, int(rect.width()), int(rect.height()))
            
            # Subtle dark glass vignette overlay
            vignette = QLinearGradient(0, 0, 0, h)
            vignette.setColorAt(0.0, QColor(0, 0, 0, 30))
            vignette.setColorAt(1.0, QColor(0, 0, 0, 80))
            painter.fillRect(self.rect(), QBrush(vignette))
        else:
            # Dark Canvas Placeholder with watermark icon
            bg_grad = QLinearGradient(0, 0, w, h)
            bg_grad.setColorAt(0.0, QColor("#1e2230"))
            bg_grad.setColorAt(1.0, QColor("#11141c"))
            painter.fillRect(self.rect(), QBrush(bg_grad))

            watermark = self.icon_pix.scaled(
                54, 54,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.setOpacity(0.35)
            painter.drawPixmap((w - 54) // 2, (h - 54) // 2, watermark)
            painter.setOpacity(1.0)

        painter.restore()

        # 2. Top-Left App Icon Badge
        icon_badge_size = 28
        badge_x, badge_y = 10, 10
        badge_rect = QRectF(badge_x, badge_y, icon_badge_size, icon_badge_size)

        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 7, 7)

        painter.fillPath(badge_path, QColor(20, 20, 25, 200))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawPath(badge_path)

        scaled_icon = self.icon_pix.scaled(
            20, 20,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(badge_x + 4, badge_y + 4, scaled_icon)

        # 3. Top-Right Workspace Pill Badge
        ws_id = self.win["workspace"]
        ws_text = f"WS {ws_id}"
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        
        ws_pill_w = 44
        ws_pill_h = 20
        ws_x = w - ws_pill_w - 10
        ws_y = 10
        ws_rect = QRectF(ws_x, ws_y, ws_pill_w, ws_pill_h)
        
        ws_path = QPainterPath()
        ws_path.addRoundedRect(ws_rect, 6, 6)
        painter.fillPath(ws_path, QColor(15, 23, 42, 210))
        painter.setPen(QPen(QColor(56, 189, 248, 120), 1))
        painter.drawPath(ws_path)

        painter.setPen(QColor("#38bdf8"))
        painter.drawText(ws_rect, Qt.AlignmentFlag.AlignCenter, ws_text)

        # 4. Selection Border & Glowing Frame
        if self.is_selected:
            # Vivid highlight border (Cyan glow)
            sel_pen = QPen(QColor("#38bdf8"), 2.5)
            painter.setPen(sel_pen)
            painter.drawPath(clip_path)

            # Subtle inner glow line
            inner_rect = QRectF(4, 4, w - 8, h - 8)
            inner_path = QPainterPath()
            inner_path.addRoundedRect(inner_rect, radius - 2, radius - 2)
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1.0))
            painter.drawPath(inner_path)
        else:
            # Subtle translucent border
            unsel_pen = QPen(QColor(255, 255, 255, 30), 1.2)
            painter.setPen(unsel_pen)
            painter.drawPath(clip_path)


# ------------------------------------------------------------------------------
# 5. Main Visual Hybrid Task Switcher HUD Window
# ------------------------------------------------------------------------------
class HybridTaskSwitcher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("omarchy-task-switcher")

        self.windows, self.monitor, self.next_free_ws = get_hyprland_data()
        self.filtered_indices = list(range(len(self.windows)))
        
        # Start selected at index 1 (MRU previous window) or 0
        self.selected_pos = 1 if len(self.windows) > 1 else 0

        self._has_focused = False
        self.init_ui()
        self.position_on_screen()
        self.update_selection()
        self.raise_()
        self.activateWindow()

        # Start live thumbnail capture in background thread
        self.thumb_worker = ThumbnailWorker(self.windows)
        self.thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumb_worker.start()

    def closeEvent(self, event):
        if hasattr(self, "thumb_worker") and self.thumb_worker.isRunning():
            self.thumb_worker.stop()
            self.thumb_worker.wait(150)
        super().closeEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._has_focused = True
            elif getattr(self, "_has_focused", False):
                self.close()
        super().changeEvent(event)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)

        # Main Frosted Glass HUD Box
        self.hud_box = QFrame()
        self.hud_box.setObjectName("MainHUD")
        self.hud_box.setStyleSheet("""
            #MainHUD {
                background-color: rgba(18, 20, 28, 0.92);
                border: 1.2px solid rgba(255, 255, 255, 0.14);
                border-radius: 20px;
            }
        """)

        # Soft drop shadow for floating elevation
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 10)
        self.hud_box.setGraphicsEffect(shadow)

        hud_layout = QVBoxLayout(self.hud_box)
        hud_layout.setContentsMargins(18, 16, 18, 14)
        hud_layout.setSpacing(12)

        # 1. Top Section: Scrollable Horizontal Strip of Window Preview Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setFixedHeight(148)

        self.cards_widget = QWidget()
        self.cards_widget.setStyleSheet("background: transparent;")
        self.cards_layout = QHBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(14)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card_widgets = []
        self._build_cards()

        self.scroll_area.setWidget(self.cards_widget)
        hud_layout.addWidget(self.scroll_area)

        # 2. Bottom Section: Info Banner about the Selected Window
        info_container = QVBoxLayout()
        info_container.setSpacing(4)
        info_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Primary Title: Window Title
        self.lbl_win_title = QLabel()
        self.lbl_win_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_win_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_win_title.setStyleSheet("color: #ffffff; letter-spacing: 0.2px;")
        info_container.addWidget(self.lbl_win_title)

        # Metadata Details: App Name • Workspace • Monitor • State
        self.lbl_meta = QLabel()
        self.lbl_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_meta.setFont(QFont("Segoe UI", 10))
        self.lbl_meta.setStyleSheet("color: #94a3b8;")
        info_container.addWidget(self.lbl_meta)

        hud_layout.addLayout(info_container)

        # 3. Subtle Footer Hints
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 0)
        footer_layout.setSpacing(8)

        hints = [
            ("⇥ Tab / ← →", "Navigate"),
            ("↵ Enter", "Focus"),
            ("Q", "Close"),
            ("N", f"New WS {self.next_free_ws}"),
            ("1-9", "Jump"),
            ("Esc", "Dismiss")
        ]

        for key_text, desc in hints:
            h_sub = QHBoxLayout()
            h_sub.setSpacing(4)

            k_lbl = QLabel(key_text)
            k_lbl.setStyleSheet("""
                color: #cbd5e1;
                background: rgba(255, 255, 255, 0.10);
                border-radius: 4px;
                padding: 1px 5px;
                font-size: 9px;
                font-weight: 700;
            """)
            d_lbl = QLabel(desc)
            d_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")
            h_sub.addWidget(k_lbl)
            h_sub.addWidget(d_lbl)
            footer_layout.addLayout(h_sub)
            footer_layout.addSpacing(4)

        footer_layout.addStretch()
        hud_layout.addLayout(footer_layout)

        root_layout.addWidget(self.hud_box)

    def _build_cards(self):
        for c in self.card_widgets:
            c.deleteLater()
        self.card_widgets = []

        if not self.filtered_indices:
            empty_lbl = QLabel("No active windows available")
            empty_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; font-style: italic; padding: 20px;")
            self.cards_layout.addWidget(empty_lbl)
            self.card_widgets.append(empty_lbl)
            return

        for pos, orig_idx in enumerate(self.filtered_indices):
            win_info = self.windows[orig_idx]
            card = WindowPreviewCard(pos, win_info, self)
            card.clicked.connect(self._on_card_clicked)
            self.card_widgets.append(card)
            self.cards_layout.addWidget(card)

    def position_on_screen(self):
        count = max(1, len(self.filtered_indices))
        hud_width = min(1300, max(520, count * 222 + 64))
        hud_height = 252
        self.resize(hud_width, hud_height)

        # Center on focused monitor
        if self.monitor:
            mon_x = self.monitor.get("x", 0)
            mon_y = self.monitor.get("y", 0)
            mon_w = self.monitor.get("width", 1920)
            mon_h = self.monitor.get("height", 1080)
            
            target_x = mon_x + (mon_w - self.width()) // 2
            target_y = mon_y + (mon_h - self.height()) // 2
            self.move(target_x, target_y)

    def update_selection(self):
        if not self.filtered_indices:
            self.lbl_win_title.setText("No Open Windows")
            self.lbl_meta.setText("")
            return

        self.selected_pos = max(0, min(self.selected_pos, len(self.filtered_indices) - 1))
        
        for pos, card in enumerate(self.card_widgets):
            if isinstance(card, WindowPreviewCard):
                card.set_selected(pos == self.selected_pos)

        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        
        # Format Title
        clean_title = win["title"]
        if len(clean_title) > 75:
            clean_title = clean_title[:72] + "..."
        self.lbl_win_title.setText(f"• {clean_title}")

        # Format Meta Details
        d_name = win.get("display_name") or win["class"]
        ws_id = win["workspace"]
        mon_name = win["monitor_name"]
        state_str = "Floating" if win["floating"] else "Tiled"
        size_w, size_h = win["size"]
        geo_str = f"{size_w}×{size_h}px" if size_w > 0 else ""

        meta_parts = [
            f"📦 {d_name}",
            f"📍 Workspace {ws_id}",
            f"🖥️ {mon_name}",
            f"🪟 {state_str}"
        ]
        if geo_str:
            meta_parts.append(f"📐 {geo_str}")

        self.lbl_meta.setText("   •   ".join(meta_parts))

        # Ensure selected card is scrolled into view
        if 0 <= self.selected_pos < len(self.card_widgets):
            card = self.card_widgets[self.selected_pos]
            self.scroll_area.ensureWidgetVisible(card, 60, 0)

    @pyqtSlot(str, str)
    def _on_thumbnail_ready(self, addr, filepath):
        for card in self.card_widgets:
            if isinstance(card, WindowPreviewCard) and card.win.get("address") == addr:
                card.set_thumbnail_file(filepath)
                break

    def _on_card_clicked(self, pos):
        self.selected_pos = pos
        self.update_selection()
        self.activate_current_window()

    def next_window(self):
        if self.filtered_indices:
            self.selected_pos = (self.selected_pos + 1) % len(self.filtered_indices)
            self.update_selection()

    def prev_window(self):
        if self.filtered_indices:
            self.selected_pos = (self.selected_pos - 1 + len(self.filtered_indices)) % len(self.filtered_indices)
            self.update_selection()

    def activate_current_window(self):
        if not self.filtered_indices:
            self.close()
            return
        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        
        addr = win["address"]
        ws = win["workspace"]
        
        # Switch workspace and focus window via hyprctl
        subprocess.run(["hyprctl", "dispatch", "workspace", str(ws)], check=False)
        subprocess.run(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"], check=False)
        self.close()

    def close_current_window(self):
        if not self.filtered_indices:
            return
        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        addr = win["address"]
        
        subprocess.run(["hyprctl", "dispatch", "closewindow", f"address:{addr}"], check=False)
        
        # Remove and refresh cards
        del self.windows[orig_idx]
        self.filtered_indices = list(range(len(self.windows)))
        if not self.windows:
            self.close()
            return
        self.selected_pos = max(0, min(self.selected_pos, len(self.filtered_indices) - 1))
        self._build_cards()
        self.position_on_screen()
        self.update_selection()

    def move_to_new_workspace(self):
        if not self.filtered_indices:
            return
        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        addr = win["address"]
        free_ws = self.next_free_ws

        subprocess.run(["hyprctl", "dispatch", "movetoworkspace", f"{free_ws},address:{addr}"], check=False)
        subprocess.run(["hyprctl", "dispatch", "workspace", str(free_ws)], check=False)
        subprocess.run(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"], check=False)
        self.close()

    def move_to_current_workspace(self):
        if not self.filtered_indices:
            return
        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        addr = win["address"]
        subprocess.run(["hyprctl", "dispatch", "movetoworkspace", f"current,address:{addr}"], check=False)
        subprocess.run(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"], check=False)
        self.close()

    # -------------------------------------------------------------------------
    # Keyboard Event Handler
    # -------------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mod = event.modifiers()

        # Escape -> Dismiss
        if key == Qt.Key.Key_Escape:
            self.close()
            return

        # Tab / Shift+Tab -> Cycle
        if key == Qt.Key.Key_Tab:
            if mod & Qt.KeyboardModifier.ShiftModifier:
                self.prev_window()
            else:
                self.next_window()
            return

        # Arrow navigation
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.next_window()
            return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.prev_window()
            return

        # Enter / Return / Space -> Activate window
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activate_current_window()
            return

        # 'Q' / Cmd+Q / Ctrl+Q / Ctrl+K / Delete -> Close app
        if key == Qt.Key.Key_Q or ((mod & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_K) or key == Qt.Key.Key_Delete:
            self.close_current_window()
            return

        # 'N' / Ctrl+N -> Move to new workspace
        if key == Qt.Key.Key_N:
            self.move_to_new_workspace()
            return

        # 'M' / Ctrl+M -> Move to current workspace
        if key == Qt.Key.Key_M:
            self.move_to_current_workspace()
            return

        # Number shortcuts 1-9 -> Jump directly
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            num_idx = key - Qt.Key.Key_1
            if num_idx < len(self.filtered_indices):
                self.selected_pos = num_idx
                self.update_selection()
                self.activate_current_window()
                return

        # Instant search / filter on typing letter
        char = event.text().lower()
        if char and char.isalnum():
            for offset in range(1, len(self.filtered_indices) + 1):
                idx = (self.selected_pos + offset) % len(self.filtered_indices)
                orig_idx = self.filtered_indices[idx]
                win = self.windows[orig_idx]
                name = (win.get("display_name") or win["class"]).lower()
                if name.startswith(char) or char in name:
                    self.selected_pos = idx
                    self.update_selection()
                    break
            return

        super().keyPressEvent(event)


# ------------------------------------------------------------------------------
# 6. Launcher Entry Point
# ------------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OmarchyTaskSwitcher")
    app.setOrganizationName("Omarchy")

    switcher = HybridTaskSwitcher()
    switcher.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
