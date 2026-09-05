# Omarchy Workspaces Preview & Native Task Switcher 🖥️✨

A powerful and elegant plugin for **[Omarchy](https://omarchy.org)** / **Hyprland** featuring:
1. 🖱️ **Status Bar Workspace Indicator & Hover Preview**
2. 🪟 **macOS-Style Live Window Task Switcher (`Super + Tab` / `Super + Alt + W`)** with live screencopy previews, app icons, and workspace info.
3. ⌨️ **Terminal TUI Mode fallback (`omarchy-workspaces-picker --tui`)**

---

## 🚀 Installationsinstruktioner (Snabbt & Enkelt)

Ge dessa enkla steg till din kompis:

### Steg 1: Klona pluginet
Kör i terminalen:
```bash
git clone https://github.com/alexwest1981/omarchy-workspaces-preview.git ~/.config/omarchy/plugins/custom.workspaces
```

---

### Steg 2: Lägg till kortkommandon
Öppna `~/.config/hypr/bindings.lua` och klistra in följande längst ner:

```lua
-- macOS-style Task Switcher med fönster-previews
hl.layer_rule({ match = { namespace = "custom.workspaces" }, no_anim = true })
o.bind("SUPER + ALT + W", "Task switch", hl.dsp.global("custom.workspaces:next"), { repeating = true })
hl.unbind("SUPER + TAB")
o.bind("SUPER + TAB", "Task switch", hl.dsp.global("custom.workspaces:next"), { repeating = true })
```

---

### Steg 3: Aktivera i panelen (`~/.config/omarchy/config.json`)
I `~/.config/omarchy/config.json`, se till att `custom.workspaces` finns med i `bar.layout.left` och under `plugins`:

```json
{
  "bar": {
    "layout": {
      "left": [
        { "id": "omarchy.menu" },
        { "id": "custom.workspaces" }
      ]
    }
  },
  "plugins": [
    { "id": "custom.workspaces" }
  ]
}
```

---

### Steg 4: Starta om och njut! 🎉
Kör detta i terminalen för att ladda ändringarna direkt:

```bash
omarchy-restart-shell && hyprctl reload
```

---

## ⌨️ Användning

- **Växla fönster:** Håll in <kbd>Super</kbd> och tryck <kbd>Tab</kbd> (eller tryck <kbd>Super</kbd> + <kbd>Alt</kbd> + <kbd>W</kbd>) för att stega mellan fönster.
- **Välj fönster:** Släpp <kbd>Super</kbd> för att direkt hoppa till fönstret och dess workspace.
- **Stäng fönster:** Tryck <kbd>Super</kbd> + <kbd>Q</kbd> medan switchern är öppen för att stänga den markerade appen.
- **Musstyrning:** Håll musen över en miniatyr och klicka för att byta direkt.

---

## 📄 Licens
MIT License © 2026 Alex Weström
