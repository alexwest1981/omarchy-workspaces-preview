# Omarchy Workspaces Preview Plugin 🖥️

A powerful and elegant plugin for **[Omarchy](https://omarchy.org)** / **Hyprland** featuring both a live **status bar hover preview** and a **keyboard-first global window picker**.

![Workspaces Preview](https://raw.githubusercontent.com/alexwest1981/omarchy-workspaces-preview/main/screenshot.png)

## ✨ Features

### 🖱️ 1. Status Bar Hover Preview
* **Instant inspection:** Move your mouse over any workspace number on the top bar to immediately see all active window titles and applications.
* **Smart Detection:** Distinguishes occupied, empty, and currently focused workspaces.
* **Native Integration:** Built with Quickshell's Hyprland IPC layer, perfectly matching Omarchy's theme.

### ⌨️ 2. Global Keyboard-First Window Picker
* **Fuzzy search across all workspaces:** Jump directly to any open window in seconds (`type` → `Enter`).
* **Auto-Workspace Switching:** Instantly switches to the target workspace and brings the selected window into focus.
* **Rich Visuals:** Displays workspace badges, application Nerd Font icons, and window titles in a sleek floating modal.

![Window Picker](https://raw.githubusercontent.com/alexwest1981/omarchy-workspaces-preview/main/picker-screenshot.png)

### 🎨 3. Live Bottom Customizer Menu
Customizable directly from the bottom footer of the window picker without leaving the app:
* `Ctrl + T` – **Theme:** *Based on System (Auto)*, *Tokyo Night*, *Catppuccin Mocha*, *Nord*, *Gruvbox*, *Cyberpunk*, *Monochrome*.
* `Ctrl + B` – **Borders & Corners:** *Rounded*, *Sharp*, *Double*, *Bold*, *None*.
* `Ctrl + S` – **Size & Margins:** *Standard*, *Compact*, *Spacious*.
* `Ctrl + I` – **Icons:** Toggle application Nerd Font icons on/off.

Preferences are automatically remembered in `~/.config/omarchy/workspaces-picker.json`.

---

## 📦 Installation

Clone this repository into your Omarchy plugins directory:

```bash
git clone https://github.com/alexwest1981/omarchy-workspaces-preview.git ~/.config/omarchy/plugins/inkedalex.workspaces-preview
```

### 1. Enable Status Bar Widget in `~/.config/omarchy/shell.json`

Replace `omarchy.workspaces` in your `bar.layout.left` with `inkedalex.workspaces-preview`:

```json
{
  "bar": {
    "layout": {
      "left": [
        { "id": "omarchy.menu" },
        { "id": "inkedalex.workspaces-preview" }
      ]
    }
  },
  "plugins": [
    { "id": "inkedalex.workspaces-preview" }
  ]
}
```

The shell will hot-reload automatically upon saving!

---

### 2. Enable Keyboard Shortcut for Window Picker

Symlink the picker script into your PATH:

```bash
ln -sf ~/.config/omarchy/plugins/inkedalex.workspaces-preview/bin/omarchy-workspaces-picker ~/.local/bin/omarchy-workspaces-picker
```

Add your preferred shortcut in `~/.config/hypr/bindings.lua`:

```lua
-- Option A: Super + Alt + W
o.bind("SUPER + ALT + W", "Window picker", "omarchy-workspaces-picker")

-- Option B: Super + W (overriding default close-window)
-- hl.unbind("SUPER + W")
-- o.bind("SUPER + W", "Window picker", "omarchy-workspaces-picker")
```

---

## 📄 License
MIT License © 2026 Alex Weström

