import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "custom.workspaces"

  property bool popupOpen: false
  property int selectedTabWs: 0  // 0 = All
  property var clientsList: []

  function close() { popupOpen = false }

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }
    return null
  }

  function workspaceIds() {
    var ids = [1, 2, 3, 4, 5]
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 0 && id <= 10 && ids.indexOf(id) === -1) ids.push(id)
    }

    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function focusWorkspace(id) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  function focusWindow(address, wsId) {
    if (!root.bar) return
    if (wsId > 0) {
      root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + wsId + "\" })"))
    }
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ window = \"address:" + address + "\" })"))
    root.close()
  }

  function closeWindow(address) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.window.close({ address = \"" + address + "\" })"))
    refreshTimer.restart()
  }

  function moveToNewWs(address) {
    if (!root.bar) return
    var occupied = {}
    for (var i = 0; i < root.clientsList.length; i++) {
      occupied[root.clientsList[i].workspace.id] = true
    }
    var freeWs = 1
    for (var w = 1; w <= 10; w++) {
      if (!occupied[w]) { freeWs = w; break; }
    }
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.window.move({ window = \"address:" + address + "\", workspace = \"" + freeWs + "\" })"))
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + freeWs + "\" })"))
    root.close()
  }

  function getAppGlyph(cls) {
    var key = String(cls || "").toLowerCase()
    if (key.indexOf("ghostty") >= 0 || key.indexOf("terminal") >= 0 || key.indexOf("alacritty") >= 0 || key.indexOf("kitty") >= 0 || key.indexOf("foot") >= 0) return "󰞷"
    if (key.indexOf("brave") >= 0 || key.indexOf("chrome") >= 0 || key.indexOf("firefox") >= 0 || key.indexOf("browser") >= 0) return "󰈹"
    if (key.indexOf("discord") >= 0 || key.indexOf("vesktop") >= 0) return "󰙯"
    if (key.indexOf("code") >= 0 || key.indexOf("cursor") >= 0 || key.indexOf("editor") >= 0 || key.indexOf("antigravity") >= 0) return "󰘐"
    if (key.indexOf("obsidian") >= 0 || key.indexOf("notes") >= 0) return "󰎞"
    if (key.indexOf("spotify") >= 0 || key.indexOf("music") >= 0) return "󰓇"
    if (key.indexOf("nautilus") >= 0 || key.indexOf("thunar") >= 0 || key.indexOf("files") >= 0) return ""
    if (key.indexOf("steam") >= 0) return "󰓓"
    if (key.indexOf("obs") >= 0) return "󰕧"
    return ""
  }

  function getCleanAppName(cls) {
    var s = String(cls || "")
    if (s.toLowerCase().indexOf("brave-discord") >= 0 || s.toLowerCase().indexOf("discord") >= 0) return "Discord"
    if (s.toLowerCase().indexOf("brave") >= 0) return "Brave Browser"
    if (s.toLowerCase().indexOf("ghostty") >= 0) return "Ghostty"
    if (s.toLowerCase().indexOf("alacritty") >= 0) return "Alacritty"
    if (s.toLowerCase().indexOf("code") >= 0) return "VS Code"
    if (s.toLowerCase().indexOf("omascribe") >= 0) return "OmaScribe"
    return s.replace(/^com\.[^.]+\./, "").replace(/^org\.[^.]+\./, "").split(".")[0] || "Window"
  }

  // ---------------------------------------------------------------------------
  // 1. Clients Fetcher
  // ---------------------------------------------------------------------------
  Process {
    id: clientsProc
    command: ["hyprctl", "clients", "-j"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var arr = JSON.parse(text.trim())
          if (Array.isArray(arr)) {
            var valid = []
            for (var i = 0; i < arr.length; i++) {
              var c = arr[i]
              if (!c.title && !c.class) continue
              if (c.workspace && c.workspace.id < 0) continue
              if (c.class === "TUI.float" || (c.title && c.title.indexOf("omarchy-workspaces-picker") >= 0)) continue
              valid.push(c)
            }
            root.clientsList = valid
          }
        } catch (e) {}
      }
    }
  }

  Timer {
    id: refreshTimer
    interval: 2000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      if (!clientsProc.running) clientsProc.running = true
    }
  }

  // Filtered window list based on selectedTabWs
  function getFilteredWindows() {
    if (root.selectedTabWs === 0) return root.clientsList
    var res = []
    for (var i = 0; i < root.clientsList.length; i++) {
      var c = root.clientsList[i]
      if (c.workspace && c.workspace.id === root.selectedTabWs) {
        res.push(c)
      }
    }
    return res
  }

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)
  implicitWidth: barRow.implicitWidth + trailingGap
  implicitHeight: barRow.implicitHeight

  // ---------------------------------------------------------------------------
  // 2. Bar Layout: Workspace Buttons + Preview Toggle Button
  // ---------------------------------------------------------------------------
  RowLayout {
    id: barRow
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap
    spacing: Style.space(2)

    // Workspace Number Buttons
    Repeater {
      model: root.workspaceIds()

      WidgetButton {
        required property int modelData

        readonly property var workspace: root.workspaceById(modelData)
        readonly property bool occupied: workspace !== null && workspace.toplevels.values.length > 0
        readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData

        bar: root.bar
        text: focused ? "\uDB85\uDCFB" : (modelData === 10 ? "0" : String(modelData))
        active: focused || (root.popupOpen && root.selectedTabWs === modelData)
        opacity: occupied || focused ? 1 : 0.5
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.vertical ? root.barSize : Style.space(20)
        fixedHeight: root.barSize
        tooltipText: "Workspace " + modelData + (occupied ? " (" + workspace.toplevels.values.length + " fönster)" : " (Tom)") + "\nKlicka för att växla, Högerklicka för lista"
        
        onPressed: function(btn) {
          if (btn === 3) {
            root.selectedTabWs = modelData
            root.popupOpen = !root.popupOpen
          } else {
            root.focusWorkspace(modelData)
          }
        }
      }
    }

    // Interactive Preview List Button
    WidgetButton {
      bar: root.bar
      text: "󰕰"
      active: root.popupOpen
      horizontalMargin: 4
      verticalPadding: 6
      fixedWidth: root.vertical ? root.barSize : Style.space(18)
      fixedHeight: root.barSize
      tooltipText: "Öppna Fönsteröversikt (" + root.clientsList.length + " fönster aktiva)"
      onPressed: function(btn) {
        root.selectedTabWs = 0
        root.popupOpen = !root.popupOpen
        if (root.popupOpen) refreshTimer.restart()
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 3. Rich Dropdown Popup Panel: Live Window List & Quick Actions
  // ---------------------------------------------------------------------------
  PopupCard {
    id: popup
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.popupOpen
    contentWidth: popup.fittedContentWidth(Style.space(420))
    contentHeight: popup.fittedContentHeight(popCol.implicitHeight)

    Column {
      id: popCol
      anchors.fill: parent
      spacing: Style.space(10)

      // Header Banner
      RowLayout {
        width: parent.width
        spacing: Style.space(8)

        BorderSurface {
          width: Style.space(36)
          height: Style.space(36)
          radius: Style.spacing.labelGap
          color: Style.normalFillFor(root.bar.foreground, Color.accent)
          borderSpec: Border.controlSpec("normal", root.bar.foreground, Color.accent)

          Text {
            anchors.centerIn: parent
            text: "󰕰"
            color: Color.accent
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.displayMedium
          }
        }

        Column {
          Layout.fillWidth: true
          spacing: Style.space(2)

          Text {
            text: "Öppna Fönster & Workspaces"
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.subtitle
            font.bold: true
          }

          Text {
            text: root.clientsList.length + " aktiva fönster totalt"
            color: Qt.darker(root.bar.foreground, 1.3)
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
        }

        Button {
          text: "🖥️ Task Switcher"
          bar: root.bar
          onClicked: {
            root.close()
            Quickshell.execDetached(["omarchy-workspaces-picker"])
          }
        }
      }

      PanelSeparator {
        width: parent.width
        bar: root.bar
      }

      // Workspace Tab Filter Strip
      RowLayout {
        width: parent.width
        spacing: Style.space(4)

        Button {
          text: "Alla (" + root.clientsList.length + ")"
          bar: root.bar
          active: root.selectedTabWs === 0
          onClicked: { root.selectedTabWs = 0 }
        }

        Repeater {
          model: root.workspaceIds()

          Button {
            required property int modelData
            readonly property var ws: root.workspaceById(modelData)
            readonly property int count: ws && ws.toplevels ? ws.toplevels.values.length : 0

            text: "WS " + modelData + (count > 0 ? " (" + count + ")" : "")
            bar: root.bar
            active: root.selectedTabWs === modelData
            dimmed: count === 0
            onClicked: { root.selectedTabWs = modelData }
          }
        }
      }

      // Window List Container
      Column {
        width: parent.width
        spacing: Style.space(6)

        // Empty state
        Item {
          width: parent.width
          height: Style.space(60)
          visible: root.getFilteredWindows().length === 0

          Text {
            anchors.centerIn: parent
            text: "Inga öppna fönster i detta workspace"
            color: Qt.darker(root.bar.foreground, 1.5)
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.body
            font.italic: true
          }
        }

        // Window Rows
        Repeater {
          model: root.getFilteredWindows()

          BorderSurface {
            id: winRow
            required property var modelData
            width: parent.width
            height: Style.space(48)
            radius: Style.spacing.labelGap
            color: winMouse.containsMouse ? Style.hoverFillFor(root.bar.background || "#1e2230", Color.accent) : Qt.darker(root.bar.background || "#1e2230", 1.1)
            borderSpec: Border.controlSpec(winMouse.containsMouse ? "hover" : "normal", root.bar.foreground, Color.accent)

            RowLayout {
              anchors.fill: parent
              anchors.margins: Style.space(8)
              spacing: Style.space(10)

              // App Icon Glyph
              Text {
                text: root.getAppGlyph(winRow.modelData.class)
                color: Color.accent
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.displayMedium
              }

              // Window Info (App name & Window Title)
              Column {
                Layout.fillWidth: true
                spacing: Style.space(2)

                Row {
                  spacing: Style.space(6)

                  Text {
                    text: root.getCleanAppName(winRow.modelData.class)
                    color: root.bar.foreground
                    font.family: root.bar.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                  }

                  BorderSurface {
                    height: Style.space(16)
                    width: wsText.implicitWidth + Style.space(8)
                    radius: Style.space(4)
                    color: Qt.rgba(0.2, 0.6, 1.0, 0.15)
                    borderSpec: Border.controlSpec("normal", Color.accent, Color.accent)

                    Text {
                      id: wsText
                      anchors.centerIn: parent
                      text: "WS " + (winRow.modelData.workspace ? winRow.modelData.workspace.id : "?")
                      color: Color.accent
                      font.family: root.bar.fontFamily
                      font.pixelSize: Style.font.caption
                      font.bold: true
                    }
                  }
                }

                Text {
                  width: winRow.width - Style.space(140)
                  text: winRow.modelData.title || "Untitled"
                  color: Qt.darker(root.bar.foreground, 1.2)
                  font.family: root.bar.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  elide: Text.ElideRight
                }
              }

              // Quick Action Buttons (New WS, Close)
              Row {
                spacing: Style.space(4)

                Button {
                  text: "✨ Nytt WS"
                  bar: root.bar
                  tooltipText: "Flytta till nästa lediga workspace"
                  onClicked: { root.moveToNewWs(winRow.modelData.address) }
                }

                Button {
                  text: "✕"
                  bar: root.bar
                  tooltipText: "Stäng fönster"
                  onClicked: { root.closeWindow(winRow.modelData.address) }
                }
              }
            }

            MouseArea {
              id: winMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              acceptedButtons: Qt.LeftButton
              onClicked: {
                var wsId = winRow.modelData.workspace ? winRow.modelData.workspace.id : 0
                root.focusWindow(winRow.modelData.address, wsId)
              }
            }
          }
        }
      }

      PanelSeparator {
        width: parent.width
        bar: root.bar
      }

      // Footer Help
      RowLayout {
        width: parent.width

        Text {
          text: "💡 Klicka på ett fönster för att hoppa direkt  •  Super + Alt + W för Task Switcher"
          color: Qt.darker(root.bar.foreground, 1.5)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
