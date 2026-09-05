#!/usr/bin/env python3
# ==============================================================================
# Omarchy macOS-Style Visual Task Switcher 🖥️✨
# Part of the Omarchy Workspaces Preview Plugin
# https://github.com/alexwest1981/omarchy-workspaces-preview
# ==============================================================================

import sys
import os
import json
import subprocess
import glob
import re
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QScrollArea, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter, QPainterPath,
    QKeySequence, QKeyEvent, QMouseEvent, QCursor
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

    # Next free workspace (1..10 or max+1)
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
        # Ignore empty/special helper windows
        ws_info = c.get("workspace", {})
        ws_id = ws_info.get("id", 0)
        title = (c.get("title") or "").strip()
        app_cls = (c.get("class") or "").strip()
        
        if not title and not app_cls:
            continue
        if ws_id < 0: # Special scratchpads if hidden
            continue
            
        valid_windows.append({
            "address": c.get("address"),
            "title": title or "Untitled Window",
            "class": app_cls or "Application",
            "initialClass": c.get("initialClass", ""),
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
# 2. High-Quality App Icon Resolver
# ------------------------------------------------------------------------------
class IconResolver:
    _cache = {}
    _desktop_map = None

    @classmethod
    def _build_desktop_map(cls):
        if cls._desktop_map is not None:
            return
        cls._desktop_map = {}
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
                        icon = None
                        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("Icon=") and not icon:
                                    icon = line.split("=", 1)[1]
                                elif line.startswith("StartupWMClass=") and icon:
                                    wm = line.split("=", 1)[1].lower()
                                    cls._desktop_map[wm] = icon
                        base = os.path.splitext(os.path.basename(fp))[0].lower()
                        if icon:
                            cls._desktop_map[base] = icon
                    except Exception:
                        pass

    @classmethod
    def resolve(cls, app_class, title=""):
        cls._build_desktop_map()
        key = (app_class or "").lower()
        if key in cls._cache:
            return cls._cache[key]

        # Clean key names (e.g. brave-discord.com... -> discord, brave)
        candidates = [app_class, key]
        if "discord" in key:
            candidates.extend(["discord", "com.discordapp.Discord"])
        if "brave" in key:
            candidates.extend(["brave-browser", "brave", "com.brave.Browser"])
        if "code" in key or "vscode" in key:
            candidates.extend(["code", "visual-studio-code", "vscode"])
        if "ghostty" in key or "alacritty" in key or "kitty" in key or "terminal" in key:
            candidates.extend([key, "utilities-terminal", "terminal", "Alacritty", "ghostty"])
        if "spotify" in key:
            candidates.extend(["spotify", "spotify-client"])
        if "omascribe" in key:
            candidates.extend(["omascribe", "accessories-text-editor"])

        # 1. Check desktop map
        for c in candidates:
            if c.lower() in cls._desktop_map:
                icon_val = cls._desktop_map[c.lower()]
                if os.path.isfile(icon_val):
                    pix = QPixmap(icon_val)
                    if not pix.isNull():
                        cls._cache[key] = pix
                        return pix
                candidates.append(icon_val)

        # 2. QIcon fromTheme
        for c in candidates:
            ic = QIcon.fromTheme(c)
            if not ic.isNull():
                pix = ic.pixmap(128, 128)
                if not pix.isNull():
                    cls._cache[key] = pix
                    return pix

        # 3. Direct filesystem search
        for c in candidates:
            patterns = [
                f"/usr/share/icons/**/{c}.*",
                f"/usr/share/icons/**/{c}-*.*",
                f"/usr/share/pixmaps/{c}.*",
                f"{os.path.expanduser('~/.local/share/icons')}/**/{c}.*",
            ]
            for p in patterns:
                for match in glob.glob(p, recursive=True):
                    if match.lower().endswith((".png", ".svg", ".xpm", ".ico")):
                        pix = QPixmap(match)
                        if not pix.isNull():
                            cls._cache[key] = pix
                            return pix

        # 4. Fallback generated stylish icon
        pix = cls._generate_fallback_badge(app_class)
        cls._cache[key] = pix
        return pix

    @classmethod
    def _generate_fallback_badge(cls, text):
        pix = QPixmap(96, 96)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Gradient background badge
        path = QPainterPath()
        path.addRoundedRect(4, 4, 88, 88, 20, 20)
        painter.fillPath(path, QColor("#1e293b"))
        painter.setPen(QColor("#3b82f6"))
        painter.drawPath(path)

        # First 1-2 characters
        char_label = (text[:2] if len(text) >= 2 else text[:1]).upper() if text else "🪟"
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        painter.drawText(0, 0, 96, 96, Qt.AlignmentFlag.AlignCenter, char_label)
        painter.end()
        return pix

# ------------------------------------------------------------------------------
# 3. Task Switcher App Card Widget
# ------------------------------------------------------------------------------
class AppCard(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, index, window_info, parent=None):
        super().__init__(parent)
        self.index = index
        self.win = window_info
        self.is_selected = False

        self.setFixedSize(148, 140)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.init_ui()
        self.update_style()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Top Badge Row (Number shortcut + Workspace Pill)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)

        num_str = str(self.index + 1) if self.index < 9 else ""
        self.lbl_num = QLabel(num_str)
        self.lbl_num.setStyleSheet("""
            color: #94a3b8;
            font-size: 10px;
            font-weight: bold;
            background: rgba(255,255,255,0.08);
            border-radius: 4px;
            padding: 1px 4px;
        """)
        self.lbl_num.setVisible(bool(num_str))
        top_row.addWidget(self.lbl_num)
        top_row.addStretch()

        ws_id = self.win["workspace"]
        self.lbl_ws = QLabel(f"WS {ws_id}")
        self.lbl_ws.setStyleSheet("""
            color: #38bdf8;
            font-size: 10px;
            font-weight: 700;
            background: rgba(56, 189, 248, 0.15);
            border-radius: 4px;
            padding: 1px 5px;
        """)
        top_row.addWidget(self.lbl_ws)
        layout.addLayout(top_row)

        # Large App Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = IconResolver.resolve(self.win["class"], self.win["title"])
        scaled_pix = pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.lbl_icon.setPixmap(scaled_pix)
        layout.addWidget(self.lbl_icon)

        # App Display Name
        app_name = self.win["class"].split(".")[-1]
        if "brave" in app_name.lower():
            app_name = "Brave"
        elif "discord" in app_name.lower():
            app_name = "Discord"
        elif "code" in app_name.lower():
            app_name = "VS Code"
        elif "omascribe" in app_name.lower():
            app_name = "OmaScribe"
        elif "alacritty" in app_name.lower():
            app_name = "Alacritty"

        self.lbl_name = QLabel(app_name[:16])
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self.lbl_name.setStyleSheet("color: #f1f5f9;")
        layout.addWidget(self.lbl_name)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet("""
                AppCard {
                    background-color: rgba(59, 130, 246, 0.28);
                    border: 2px solid #60a5fa;
                    border-radius: 14px;
                }
            """)
        else:
            self.setStyleSheet("""
                AppCard {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 14px;
                }
                AppCard:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                    border-color: rgba(255, 255, 255, 0.25);
                }
            """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

# ------------------------------------------------------------------------------
# 4. Main macOS Task Switcher Overlay Window
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
        self.setObjectName("TaskSwitcherHUD")

        self.windows, self.monitor, self.next_free_ws = get_hyprland_data()
        self.filtered_indices = list(range(len(self.windows)))
        
        # Start selected at index 1 (previous app in MRU order) or 0
        self.selected_pos = 1 if len(self.windows) > 1 else 0

        self.init_ui()
        self.position_on_screen()
        self.update_selection()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self.close()
        super().changeEvent(event)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)

        # Main Glass Container
        self.glass_box = QFrame()
        self.glass_box.setObjectName("GlassContainer")
        self.glass_box.setStyleSheet("""
            #GlassContainer {
                background-color: rgba(15, 18, 26, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 20px;
            }
        """)

        # Drop shadow for floating HUD elevation
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 12)
        self.glass_box.setGraphicsEffect(shadow)

        glass_layout = QVBoxLayout(self.glass_box)
        glass_layout.setContentsMargins(24, 20, 24, 18)
        glass_layout.setSpacing(14)

        # 1. Header Bar: Title + Search input
        header = QHBoxLayout()
        header.setSpacing(12)

        lbl_hud_title = QLabel("🖥️  App Switcher")
        lbl_hud_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_hud_title.setStyleSheet("color: #94a3b8; letter-spacing: 0.5px;")
        header.addWidget(lbl_hud_title)

        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Type to filter...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
                background: rgba(255, 255, 255, 0.12);
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_input)

        glass_layout.addLayout(header)

        # 2. Scrollable Cards Container (Horizontal Row / Wrap Grid)
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_scroll.setStyleSheet("background: transparent;")

        self.cards_widget = QWidget()
        self.cards_widget.setStyleSheet("background: transparent;")
        self.cards_layout = QHBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 6, 0, 6)
        self.cards_layout.setSpacing(14)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card_widgets = []
        self._build_cards()

        self.cards_scroll.setWidget(self.cards_widget)
        glass_layout.addWidget(self.cards_scroll)

        # 3. Active Window Detail Banner
        self.detail_frame = QFrame()
        self.detail_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 8px 12px;
            }
        """)
        detail_layout = QVBoxLayout(self.detail_frame)
        detail_layout.setContentsMargins(10, 8, 10, 8)
        detail_layout.setSpacing(4)

        self.lbl_active_title = QLabel()
        self.lbl_active_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_active_title.setStyleSheet("color: #ffffff;")
        self.lbl_active_title.setWordWrap(True)
        detail_layout.addWidget(self.lbl_active_title)

        self.lbl_active_meta = QLabel()
        self.lbl_active_meta.setFont(QFont("Segoe UI", 10))
        self.lbl_active_meta.setStyleSheet("color: #94a3b8;")
        detail_layout.addWidget(self.lbl_active_meta)

        glass_layout.addWidget(self.detail_frame)

        # 4. Keyboard Shortcuts Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)
        
        hints = [
            ("⇥ Tab / ← →", "Navigate"),
            ("↵ Enter", "Focus"),
            ("Ctrl + N", f"New WS {self.next_free_ws}"),
            ("Ctrl + K", "Close"),
            ("Esc", "Cancel")
        ]

        for key_badge, label in hints:
            h_box = QHBoxLayout()
            h_box.setSpacing(4)
            kb = QLabel(key_badge)
            kb.setStyleSheet("""
                color: #e2e8f0;
                background: rgba(255,255,255,0.12);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            """)
            txt = QLabel(label)
            txt.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
            h_box.addWidget(kb)
            h_box.addWidget(txt)
            footer.addLayout(h_box)
            footer.addSpacing(6)

        footer.addStretch()
        glass_layout.addLayout(footer)

        root_layout.addWidget(self.glass_box)

    def _build_cards(self):
        # Clear existing
        for c in self.card_widgets:
            c.deleteLater()
        self.card_widgets = []

        if not self.filtered_indices:
            empty_lbl = QLabel("No active windows matching filter")
            empty_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; font-style: italic; padding: 24px;")
            self.cards_layout.addWidget(empty_lbl)
            self.card_widgets.append(empty_lbl)
            return

        for pos, orig_idx in enumerate(self.filtered_indices):
            win_info = self.windows[orig_idx]
            card = AppCard(pos, win_info, self)
            card.clicked.connect(self._on_card_clicked)
            self.card_widgets.append(card)
            self.cards_layout.addWidget(card)

    def position_on_screen(self):
        card_count = max(1, len(self.filtered_indices))
        calc_width = min(1100, max(560, card_count * 162 + 80))
        self.resize(calc_width, 360)

        # Center on active monitor
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
            self.lbl_active_title.setText("No window selected")
            self.lbl_active_meta.setText("")
            return

        self.selected_pos = max(0, min(self.selected_pos, len(self.filtered_indices) - 1))
        
        for pos, card in enumerate(self.card_widgets):
            if isinstance(card, AppCard):
                card.set_selected(pos == self.selected_pos)

        # Update details banner
        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        self.lbl_active_title.setText(win["title"])
        
        state_str = "Floating" if win["floating"] else "Tiled"
        self.lbl_active_meta.setText(
            f"📍 Workspace {win['workspace']}  •  🖥️ {win['monitor_name']}  •  🪟 {state_str}  •  PID {win['pid']}"
        )

    def _on_search_changed(self, query):
        q = query.strip().lower()
        if not q:
            self.filtered_indices = list(range(len(self.windows)))
        else:
            self.filtered_indices = [
                i for i, w in enumerate(self.windows)
                if q in w["class"].lower() or q in w["title"].lower() or q in str(w["workspace"])
            ]
        self.selected_pos = 0
        self._build_cards()
        self.position_on_screen()
        self.update_selection()

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
        
        # Switch workspace and focus window
        subprocess.run(["hyprctl", "dispatch", "workspace", str(ws)], check=False)
        subprocess.run(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"], check=False)
        self.close()

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

    def close_current_window(self):
        if not self.filtered_indices:
            return
        orig_idx = self.filtered_indices[self.selected_pos]
        win = self.windows[orig_idx]
        addr = win["address"]
        subprocess.run(["hyprctl", "dispatch", "closewindow", f"address:{addr}"], check=False)
        
        # Remove from local list and refresh
        del self.windows[orig_idx]
        self.filtered_indices = list(range(len(self.windows)))
        if not self.windows:
            self.close()
            return
        self.selected_pos = max(0, min(self.selected_pos, len(self.filtered_indices) - 1))
        self._build_cards()
        self.position_on_screen()
        self.update_selection()

    # -------------------------------------------------------------------------
    # Keyboard Event Handler
    # -------------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mod = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.close()
            return

        # Navigate with Tab / Shift+Tab
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

        # Enter / Return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activate_current_window()
            return

        # Number shortcuts 1-9
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            num_idx = key - Qt.Key.Key_1
            if num_idx < len(self.filtered_indices):
                self.selected_pos = num_idx
                self.update_selection()
                self.activate_current_window()
                return

        # Ctrl+N -> New Workspace
        if (mod & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_N:
            self.move_to_new_workspace()
            return

        # Ctrl+K / Delete -> Kill/Close Window
        if ((mod & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_K) or key == Qt.Key.Key_Delete:
            self.close_current_window()
            return

        # Ctrl+M -> Move to Current Workspace
        if (mod & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_M:
            self.move_to_current_workspace()
            return

        # Type to search redirect
        if not self.search_input.hasFocus() and (event.text().isalnum() or key == Qt.Key.Key_Backspace):
            self.search_input.setFocus()
            self.search_input.event(event)
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
