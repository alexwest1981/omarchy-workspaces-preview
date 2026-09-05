#!/usr/bin/env python3
# ==============================================================================
# Omarchy macOS-Style Visual Task Switcher 🖥️✨
# Authentic Command-Tab HUD for Omarchy / Hyprland
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
    QScrollArea, QFrame, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter, QPainterPath,
    QKeyEvent, QMouseEvent, QCursor
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
    for m in monitors:
        mon_map[m.get("id")] = m.get("description") or m.get("model") or m.get("name") or "Screen"
        if m.get("focused"):
            focused_mon = m
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
            "size": c.get("size", [0, 0])
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

        # 1. Desktop files index
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

        # 2. High-res icon index
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

        # Check desktop map for app_class and initial_class
        for search_k in [key, (initial_class or "").lower()]:
            if search_k in cls._desktop_map:
                icon_val, d_name = cls._desktop_map[search_k]
                if icon_val:
                    candidates.insert(0, icon_val)
                if d_name:
                    display_name = d_name

        # Webapp & specialized alias handling
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

        # 1. Search candidates in indexed icon paths or direct file paths
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

        # 2. Try QIcon.fromTheme
        for c in candidates:
            if not c:
                continue
            ic = QIcon.fromTheme(c)
            if not ic.isNull():
                pix = ic.pixmap(128, 128)
                if not pix.isNull():
                    cls._pixmap_cache[key] = (pix, display_name)
                    return pix, display_name

        # 3. Fallback stylish badge
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
# 3. Authentic macOS App Switcher Tile
# ------------------------------------------------------------------------------
class AppTile(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, index, window_info, parent=None):
        super().__init__(parent)
        self.index = index
        self.win = window_info
        self.is_selected = False
        self.display_name = "App"

        self.setFixedSize(92, 92)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.init_ui()
        self.update_style()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # App Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        pix, d_name = IconResolver.resolve(
            self.win["class"], 
            self.win.get("initialClass", ""), 
            self.win["title"]
        )
        self.display_name = d_name
        self.win["display_name"] = d_name

        scaled_pix = pix.scaled(
            64, 64, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_icon.setPixmap(scaled_pix)
        layout.addWidget(self.lbl_icon)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update_style()

    def update_style(self):
        if self.is_selected:
            # Authentic macOS Command-Tab highlight pill
            self.setStyleSheet("""
                AppTile {
                    background-color: rgba(255, 255, 255, 0.22);
                    border: 1.5px solid rgba(255, 255, 255, 0.35);
                    border-radius: 18px;
                }
            """)
        else:
            self.setStyleSheet("""
                AppTile {
                    background-color: transparent;
                    border: 1.5px solid transparent;
                    border-radius: 18px;
                }
                AppTile:hover {
                    background-color: rgba(255, 255, 255, 0.10);
                    border-color: rgba(255, 255, 255, 0.15);
                }
            """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)


# ------------------------------------------------------------------------------
# 4. Main macOS Command-Tab HUD Window
# ------------------------------------------------------------------------------
class MacOSTaskSwitcher(QWidget):
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
        
        # Start selected at index 1 (the MRU previous window) or 0
        self.selected_pos = 1 if len(self.windows) > 1 else 0

        self.init_ui()
        self.position_on_screen()
        self.update_selection()

    def changeEvent(self, event):
        # Dismiss immediately if switcher loses focus
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self.close()
        super().changeEvent(event)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)

        # Main macOS Frosted Glass HUD Container
        self.hud_box = QFrame()
        self.hud_box.setObjectName("MacOS_HUD")
        self.hud_box.setStyleSheet("""
            #MacOS_HUD {
                background-color: rgba(25, 25, 28, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 22px;
            }
        """)

        # Soft drop shadow for floating elevation
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 10)
        self.hud_box.setGraphicsEffect(shadow)

        hud_layout = QVBoxLayout(self.hud_box)
        hud_layout.setContentsMargins(18, 16, 18, 14)
        hud_layout.setSpacing(10)
        hud_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. Horizontal Strip of App Tiles
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.tiles_widget = QWidget()
        self.tiles_widget.setStyleSheet("background: transparent;")
        self.tiles_layout = QHBoxLayout(self.tiles_widget)
        self.tiles_layout.setContentsMargins(6, 4, 6, 4)
        self.tiles_layout.setSpacing(10)
        self.tiles_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.tile_widgets = []
        self._build_tiles()

        self.scroll_area.setWidget(self.tiles_widget)
        hud_layout.addWidget(self.scroll_area)

        # 2. macOS Active App Name & Window Title Display
        self.lbl_app_name = QLabel()
        self.lbl_app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_app_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_app_name.setStyleSheet("color: #ffffff; letter-spacing: 0.3px;")
        hud_layout.addWidget(self.lbl_app_name)

        self.lbl_sub_title = QLabel()
        self.lbl_sub_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_title.setFont(QFont("Segoe UI", 10))
        self.lbl_sub_title.setStyleSheet("color: #a1a1aa;")
        hud_layout.addWidget(self.lbl_sub_title)

        root_layout.addWidget(self.hud_box)

    def _build_tiles(self):
        for t in self.tile_widgets:
            t.deleteLater()
        self.tile_widgets = []

        if not self.filtered_indices:
            empty_lbl = QLabel("No active windows")
            empty_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; font-style: italic; padding: 20px;")
            self.tiles_layout.addWidget(empty_lbl)
            self.tile_widgets.append(empty_lbl)
            return

        for pos, orig_idx in enumerate(self.filtered_indices):
            win_info = self.windows[orig_idx]
            tile = AppTile(pos, win_info, self)
            tile.clicked.connect(self._on_tile_clicked)
            self.tile_widgets.append(tile)
            self.tiles_layout.addWidget(tile)

    def position_on_screen(self):
        count = max(1, len(self.filtered_indices))
        # HUD dynamically sizes based on number of items, bounded between 320px and 1000px
        hud_width = min(1020, max(340, count * 102 + 64))
        hud_height = 190
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
            self.lbl_app_name.setText("No Open Windows")
            self.lbl_sub_title.setText("")
            return

        self.selected_pos = max(0, min(self.selected_pos, len(self.filtered_indices) - 1))
        
        for pos, tile in enumerate(self.tile_widgets):
            if isinstance(tile, AppTile):
                tile.set_selected(pos == self.selected_pos)

        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        
        d_name = win.get("display_name") or win["class"]
        self.lbl_app_name.setText(d_name)

        # Clean subtitle with workspace & truncated window title
        clean_title = win["title"]
        if len(clean_title) > 55:
            clean_title = clean_title[:52] + "..."
        ws_badge = f"Workspace {win['workspace']}"
        self.lbl_sub_title.setText(f"{ws_badge}  •  {clean_title}")

        # Ensure selected tile is scrolled into view
        if 0 <= self.selected_pos < len(self.tile_widgets):
            tile = self.tile_widgets[self.selected_pos]
            self.scroll_area.ensureWidgetVisible(tile, 50, 0)

    def _on_tile_clicked(self, pos):
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
        
        # Remove and refresh tiles
        del self.windows[orig_idx]
        self.filtered_indices = list(range(len(self.windows)))
        if not self.windows:
            self.close()
            return
        self.selected_pos = max(0, min(self.selected_pos, len(self.filtered_indices) - 1))
        self._build_tiles()
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

        # 'Q' / Cmd+Q / Ctrl+Q / Ctrl+K / Delete -> Close app (like macOS Cmd+Tab + Q)
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
            # Find next app matching character
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
# 5. Launcher Entry Point
# ------------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OmarchyTaskSwitcher")
    app.setOrganizationName("Omarchy")

    switcher = MacOSTaskSwitcher()
    switcher.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
