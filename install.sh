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
        git -C "$PLUGIN_DIR" pull --ff-only || true
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
BINDINGS_FILE="$HOME/.config/hypr/bindings.lua"
if [ -f "$BINDINGS_FILE" ]; then
    if ! grep -q "custom.workspaces" "$BINDINGS_FILE"; then
        echo "⌨️ Lägger till kortkommandon i bindings.lua..."
        cat << 'BINDINGS_EOF' >> "$BINDINGS_FILE"

-- macOS-style Task Switcher (custom.workspaces)
hl.layer_rule({ match = { namespace = "custom.workspaces" }, no_anim = true })
o.bind("SUPER + ALT + W", "Task switch", hl.dsp.global("custom.workspaces:next"), { repeating = true })
hl.unbind("SUPER + TAB")
o.bind("SUPER + TAB", "Task switch", hl.dsp.global("custom.workspaces:next"), { repeating = true })
BINDINGS_EOF
    else
        echo "✔ Kortkommandon finns redan i bindings.lua"
    fi
fi

# 3. Enable in ~/.config/omarchy/config.json
CONFIG_FILE="$HOME/.config/omarchy/config.json"
if [ -f "$CONFIG_FILE" ] && command -v jq >/dev/null 2>&1; then
    echo "⚙️ Aktiverar plugin i Omarchy-konfigurationen..."
    # Ensure plugin is in plugins list
    if ! jq -e '.plugins[] | select(.id == "custom.workspaces")' "$CONFIG_FILE" >/dev/null 2>&1; then
        tmp=$(mktemp)
        jq '.plugins += [{"id": "custom.workspaces"}]' "$CONFIG_FILE" > "$tmp" && mv "$tmp" "$CONFIG_FILE"
    fi
    # Ensure custom.workspaces is in bar.layout.left
    if ! jq -e '.bar.layout.left[] | select(.id == "custom.workspaces")' "$CONFIG_FILE" >/dev/null 2>&1; then
        tmp=$(mktemp)
        jq 'if (.bar.layout.left[] | select(.id == "omarchy.workspaces")) then (.bar.layout.left |= map(if .id == "omarchy.workspaces" then {"id": "custom.workspaces"} else . end)) else (.bar.layout.left += [{"id": "custom.workspaces"}]) end' "$CONFIG_FILE" > "$tmp" && mv "$tmp" "$CONFIG_FILE"
    fi
fi

# 4. Restart shell and reload Hyprland
echo "🔄 Startar om Omarchy shell och laddar om Hyprland..."
omarchy-restart-shell 2>/dev/null || true
hyprctl reload 2>/dev/null || true

echo ""
echo -e "\033[1;32m================================================================\033[0m"
echo -e "\033[1;32m ✨ Installationen är klar!\033[0m"
echo -e "\033[1;37m • Håll in Super och tryck Tab för att växla appar\033[0m"
echo -e "\033[1;37m • Tryck Super + Alt + W för att öppna Task Switcher\033[0m"
echo -e "\033[1;32m================================================================\033[0m"
