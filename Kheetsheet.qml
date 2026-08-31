import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons

// Overlay plugin: shows the currently focused app's real keyboard shortcuts,
// pulled live from com.kheetsheet.Daemon (this project's own AT-SPI-reading
// D-Bus service, ported from https://github.com/Doghouse-Mike/kheetsheet).
// Talks to the daemon over `busctl --json=short` rather than a direct D-Bus
// binding: Quickshell has no generic D-Bus client QML type (checked - only
// Quickshell.DBusMenu exists, which is special-purpose), and this is the
// same "shell out, parse JSON" idiom sinkeat.keysmith already uses for its
// own helper binaries.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false

  property string appName: ""
  property var items: []
  property var groupedItems: []
  property string loadError: ""
  property bool loading: false
  property int selectedIndex: -1
  property string filterText: ""
  // Set once a native-overlay attempt has been made for the current
  // open() session, successful or not, so the offer isn't repeated after
  // a failure within the same sitting.
  property bool nativeAttempted: false

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color borderColor: Color.menu.border
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  property string fontFamily: Style.font.menuFamily

  readonly property var filtered: {
    var q = root.filterText.toLowerCase()
    if (!q) return root.items
    return root.items.filter(function (it) {
      return it.label.toLowerCase().indexOf(q) !== -1
        || it.group.toLowerCase().indexOf(q) !== -1
    })
  }

  function rebuildModel() {
    listModel.clear()
    var list = root.filtered
    for (var i = 0; i < list.length; i++) {
      listModel.append({
        groupName: list[i].group,
        label: list[i].label,
        key: list[i].key,
        itemIndex: root.items.indexOf(list[i])
      })
    }
    root.selectedIndex = listModel.count > 0 ? 0 : -1
  }

  function setFilter(text) {
    root.filterText = text
    rebuildModel()
  }

  Process {
    id: fetchProc
    command: ["busctl", "--user", "--json=short", "call",
              "com.kheetsheet.Daemon", "/KheetSheet",
              "com.kheetsheet.Daemon", "GetShortcuts"]
    stdout: StdioCollector { id: fetchOut }
    stderr: StdioCollector { id: fetchErr }
    onExited: function (exitCode) {
      root.loading = false
      if (exitCode !== 0) {
        root.loadError = "Couldn't reach the kheetsheet daemon — is kheetsheet-hyprd running?"
        root.appName = ""
        root.items = []
        rebuildModel()
        return
      }
      try {
        var envelope = JSON.parse(fetchOut.text)
        var payload = JSON.parse(envelope.data[0])
        root.appName = payload.app || ""
        root.items = payload.items || []
        root.loadError = root.appName === "" ? "No active window known" : ""
      } catch (e) {
        root.loadError = "Couldn't parse the daemon's response"
        root.appName = ""
        root.items = []
      }
      rebuildModel()
    }
  }

  Process {
    id: invokeProc
    command: ["busctl", "--user", "call",
              "com.kheetsheet.Daemon", "/KheetSheet",
              "com.kheetsheet.Daemon", "InvokeShortcut", "i", "0"]
  }

  function activate(itemIndex) {
    if (itemIndex < 0 || itemIndex >= root.items.length) return
    invokeProc.command = ["busctl", "--user", "call",
                          "com.kheetsheet.Daemon", "/KheetSheet",
                          "com.kheetsheet.Daemon", "InvokeShortcut", "i", String(itemIndex)]
    invokeProc.running = true
    root.dismiss()
  }

  function activateSelected() {
    if (root.selectedIndex < 0 || root.selectedIndex >= listModel.count) return
    root.activate(listModel.get(root.selectedIndex).itemIndex)
  }

  // Opt-in only, explicit and user-triggered - see HANDOVER.md for the full
  // reasoning. This is the one path in the whole plugin that results in a
  // real synthetic key event being sent to whatever app was focused, via
  // the daemon's TryNativeOverlay. Closing this panel first (opened=false)
  // is required, not cosmetic: WlrKeyboardFocus.Exclusive means this panel
  // holds real Wayland keyboard focus while shown, and the target app must
  // hold it instead for the daemon's synthetic keypress to actually reach
  // it rather than being swallowed here.
  //
  // Deliberately does not scrape or re-render whatever the app then shows -
  // it just triggers the app's own native shortcuts overlay and leaves it
  // on screen, unthemed, for the user to close themselves. Kheetsheet only
  // reopens itself here if the attempt failed outright, to report why.
  Process {
    id: nativeProc
    command: ["busctl", "--user", "--json=short", "call",
              "com.kheetsheet.Daemon", "/KheetSheet",
              "com.kheetsheet.Daemon", "TryNativeOverlay"]
    stdout: StdioCollector { id: nativeOut }
    onExited: function (exitCode) {
      root.loading = false
      var ok = false
      var error = "Couldn't reach the kheetsheet daemon."
      if (exitCode === 0) {
        try {
          var envelope = JSON.parse(nativeOut.text)
          var payload = JSON.parse(envelope.data[0])
          ok = payload.ok === true
          error = payload.error || "Couldn't open the native overlay."
        } catch (e) {
          error = "Couldn't parse the daemon's response"
        }
      }
      if (!ok) {
        root.opened = true
        root.loadError = error
        rebuildModel()
        Qt.callLater(function () { keyCatcher.forceActiveFocus() })
      }
    }
  }

  function tryNativeOverlay() {
    if (root.nativeAttempted) return
    root.nativeAttempted = true
    root.loading = true
    root.loadError = ""
    // Release exclusive keyboard focus (hides this panel) so the target
    // app can actually receive the synthetic keypress the daemon is about
    // to send it. Only reopened by nativeProc.onExited on failure.
    root.opened = false
    nativeProc.running = true
  }

  function open(payloadJson) {
    root.opened = true
    root.filterText = ""
    root.appName = ""
    root.items = []
    root.loadError = ""
    root.loading = true
    root.nativeAttempted = false
    listModel.clear()
    root.selectedIndex = -1
    fetchProc.running = true
    Qt.callLater(function () { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
  }

  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "doghouse-mike.kheetsheet")
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  ListModel { id: listModel }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "kheetsheet"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    Rectangle {
      id: card
      width: Math.min(Style.space(520), panel.width - Style.gapsOut * 2)
      height: Math.min(Style.space(600), panel.height - Style.gapsOut * 2)
      anchors.centerIn: parent
      radius: Style.cornerRadius
      color: root.background
      border.color: root.borderColor
      border.width: 1

      MouseArea { anchors.fill: parent; onClicked: {} }

      Column {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.space(8)

        Text {
          width: parent.width
          elide: Text.ElideRight
          text: root.appName ? root.appName : (root.filterText.length ? root.filterText : "kheetsheet")
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.title
        }

        Text {
          width: parent.width
          visible: root.filterText.length > 0
          text: root.filterText
          color: root.foreground
          opacity: 0.6
          font.family: root.fontFamily
        }

        Rectangle {
          width: parent.width
          height: 1
          color: root.borderColor
          opacity: 0.5
        }

        Text {
          visible: root.loading
          width: parent.width
          text: "Reading shortcuts…"
          color: root.foreground
          opacity: 0.6
          font.family: root.fontFamily
        }

        Column {
          visible: !root.loading && root.items.length === 0
          width: parent.width
          spacing: Style.space(8)

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: root.loadError.length > 0
              ? root.loadError
              : "No shortcuts found — " + root.appName + " doesn't expose its menu to the accessibility tree."
            color: root.foreground
            opacity: 0.6
            font.family: root.fontFamily
          }

          // Opt-in only: never triggered automatically. Hides this panel and
          // sends a real synthetic keypress to the app that was focused
          // before this overlay opened, to try its own native shortcuts
          // dialog (GTK4/libadwaita apps commonly have one on
          // Ctrl+Shift+/). That dialog is left on screen as-is, unthemed -
          // this project doesn't read or re-render it. See HANDOVER.md.
          Text {
            visible: !root.nativeAttempted
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Try " + (root.appName || "this app") + "'s own shortcuts overlay"
            color: root.foreground
            opacity: nativeHint.containsMouse ? 1.0 : 0.75
            font.family: root.fontFamily
            font.underline: true

            MouseArea {
              id: nativeHint
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.tryNativeOverlay()
            }
          }
        }

        ListView {
          id: list
          visible: !root.loading && root.items.length > 0
          width: parent.width
          height: parent.height - Style.space(90)
          clip: true
          model: listModel
          currentIndex: root.selectedIndex

          section.property: "groupName"
          section.criteria: ViewSection.FullString
          section.delegate: Rectangle {
            width: list.width
            height: Style.space(24)
            color: "transparent"
            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(4)
              anchors.verticalCenter: parent.verticalCenter
              text: section
              color: root.foreground
              opacity: 0.55
              font.family: root.fontFamily
              font.bold: true
            }
          }

          delegate: Rectangle {
            required property int index
            required property string label
            required property string key
            required property int itemIndex
            width: ListView.view.width
            height: Style.space(26)
            color: index === root.selectedIndex ? root.selectedBackground : "transparent"

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(10)
              anchors.right: shortcutText.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              elide: Text.ElideRight
              text: label
              color: index === root.selectedIndex ? root.selectedText : root.foreground
              font.family: root.fontFamily
            }

            Text {
              id: shortcutText
              anchors.right: parent.right
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: key
              color: index === root.selectedIndex ? root.selectedText : root.foreground
              opacity: 0.6
              font.family: root.fontFamily
            }

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onContainsMouseChanged: if (containsMouse) root.selectedIndex = index
              onClicked: root.activate(itemIndex)
            }
          }
        }
      }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function (event) {
          if (event.key === Qt.Key_Escape) {
            if (root.filterText) root.setFilter("")
            else root.dismiss()
            event.accepted = true
          } else if (event.key === Qt.Key_Down) {
            if (root.selectedIndex < listModel.count - 1) root.selectedIndex++
            event.accepted = true
          } else if (event.key === Qt.Key_Up) {
            if (root.selectedIndex > 0) root.selectedIndex--
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (root.items.length === 0 && !root.nativeAttempted && !root.loading)
              root.tryNativeOverlay()
            else
              root.activateSelected()
            event.accepted = true
          } else if (event.key === Qt.Key_Backspace) {
            root.setFilter(root.filterText.slice(0, -1))
            event.accepted = true
          } else if (event.text && event.text.length === 1
                     && event.text.charCodeAt(0) >= 32
                     && event.text.charCodeAt(0) !== 127) {
            root.setFilter(root.filterText + event.text)
            event.accepted = true
          }
        }
      }
    }
  }
}
