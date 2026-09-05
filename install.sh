#!/usr/bin/env bash
# ==============================================================================
# 🚀 1-Click Installer for Omarchy Workspaces & Task Switcher
# https://github.com/alexwest1981/omarchy-workspaces-preview
# ==============================================================================

set -euo pipefail

echo -e "\033[1;36m================================================================\033[0m"
echo -e "\033[1;32m 🚀 Installing Omarchy Workspaces Preview & Task Switcher...   \033[0m"
echo -e "\033[1;36m================================================================\033[0m"

PLUGIN_DIR="$HOME/.config/omarchy/plugins/custom.workspaces"
REPO_URL="https://github.com/alexwest1981/omarchy-workspaces-preview.git"

# 1. Clone or update repository
mkdir -p "$HOME/.config/omarchy/plugins"
if [ -d "$PLUGIN_DIR" ]; then
    if [ -d "$PLUGIN_DIR/.git" ]; then
        echo "📦 Uppdaterar befintligt plugin..."
        git -C "$PLUGIN_DIR" pull --ff-only || (cd "$PLUGIN_DIR" && git fetch origin main && git reset --hard origin/main) || true
    else
        echo "📦 Installerar plugin..."
        rm -rf "$PLUGIN_DIR"
        git clone "$REPO_URL" "$PLUGIN_DIR"
    fi
else
    echo "📦 Laddar ned plugin..."
    git clone "$REPO_URL" "$PLUGIN_DIR"
fi

# 2. Add Hyprland keybindings
mkdir -p "$HOME/.config/hypr"
BINDINGS_FILE="$HOME/.config/hypr/bindings.lua"
if [ ! -f "$BINDINGS_FILE" ]; then
    touch "$BINDINGS_FILE"
fi

if ! grep -q "custom.workspaces" "$BINDINGS_FILE"; then
    echo "⌨️ Lägger till kortkommandon i bindings.lua..."
    cat << 'BINDINGS_EOF' >> "$BINDINGS_FILE"

-- macOS-style Task Switcher (custom.workspaces)
hl.layer_rule({ match = { namespace = "custom.workspaces" }, no_anim = true })
o.bind("SUPER + ALT + W", "Task switch (persistent)", hl.dsp.global("custom.workspaces:toggle"))
hl.unbind("SUPER + TAB")
o.bind("SUPER + TAB", "Task switch", hl.dsp.global("custom.workspaces:next"), { repeating = true })
BINDINGS_EOF
else
    echo "✔ Kortkommandon finns redan i bindings.lua"
fi

# 3. Enable in ~/.config/omarchy/shell.json (and ~/.config/omarchy/config.json)
echo "⚙️ Aktiverar plugin i Omarchy shell.json..."
python3 - << 'PYEOF'
import json, os

shell_paths = [
    os.path.expanduser("~/.config/omarchy/shell.json"),
    os.path.expanduser("~/.config/omarchy/config.json")
]

default_template = "/usr/share/omarchy/config/omarchy/shell.json"

for path in shell_paths:
    # If shell.json doesn't exist, populate from default template
    if not os.path.exists(path):
        if "shell.json" in path:
            if os.path.exists(default_template):
                try:
                    with open(default_template, "r") as f:
                        data = json.load(f)
                except Exception:
                    data = {"version": 1, "bar": {"position": "top", "layout": {"left": [{"id": "custom.workspaces"}]}}, "plugins": []}
            else:
                data = {"version": 1, "bar": {"position": "top", "layout": {"left": [{"id": "custom.workspaces"}]}}, "plugins": []}
        else:
            continue
    else:
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            continue

    if not isinstance(data, dict):
        continue

    # 1. Ensure plugin is in plugins list
    plugins = data.setdefault("plugins", [])
    if isinstance(plugins, list):
        if not any(isinstance(p, dict) and p.get("id") == "custom.workspaces" for p in plugins):
            plugins.append({"id": "custom.workspaces"})

    # 2. Ensure custom.workspaces is in bar.layout.left
    bar = data.setdefault("bar", {})
    if isinstance(bar, dict):
        layout = bar.setdefault("layout", {})
        if isinstance(layout, dict):
            left = layout.setdefault("left", [])
            if isinstance(left, list):
                has_custom = any(isinstance(w, dict) and w.get("id") == "custom.workspaces" for w in left)
                if not has_custom:
                    new_left = []
                    replaced = False
                    for w in left:
                        if isinstance(w, dict) and w.get("id") == "omarchy.workspaces":
                            new_left.append({"id": "custom.workspaces"})
                            replaced = True
                        else:
                            new_left.append(w)
                    if not replaced:
                        new_left.append({"id": "custom.workspaces"})
                    layout["left"] = new_left

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✔ Uppdaterade {path}")
PYEOF

# 4. Restart shell and reload Hyprland
echo "🔄 Startar om Omarchy shell och laddar om Hyprland..."
omarchy-restart-shell 2>/dev/null || omarchy restart shell 2>/dev/null || true
hyprctl reload 2>/dev/null || true

echo ""
echo -e "\033[1;32m================================================================\033[0m"
echo -e "\033[1;32m ✨ Installationen är klar!\033[0m"
echo -e "\033[1;37m • Håll in Super och tryck Tab för att växla appar\033[0m"
echo -e "\033[1;37m • Tryck Super + Alt + W för att öppna Task Switcher\033[0m"
echo -e "\033[1;32m================================================================\033[0m"
