# Omarchy Workspaces Preview Plugin 🖥️

A lightweight and elegant status bar plugin for **[Omarchy](https://omarchy.org)** / **Hyprland** that provides a live **hover preview of all open windows** inside each workspace.

![Workspaces Preview](https://raw.githubusercontent.com/alexwest1981/omarchy-workspaces-preview/main/screenshot.png)

## ✨ Features
* **Hover Preview:** Move your mouse over any workspace number to immediately see a neat list of all active window titles and app names.
* **Smart Detection:** Automatically distinguishes occupied, empty, and currently focused workspaces.
* **Native Integration:** Uses Quickshell's Hyprland IPC layer and matches Omarchy's design language and theme.

## 📦 Installation

Clone this repository into your Omarchy plugins directory:

```bash
git clone https://github.com/alexwest1981/omarchy-workspaces-preview.git ~/.config/omarchy/plugins/inkedalex.workspaces-preview
```

### Enable in `~/.config/omarchy/shell.json`

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

## 📄 License
MIT License © 2026 Alex Weström
