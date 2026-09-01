.pragma library

// Lightweight, dependency-free i18n for this plugin. Not Qt Linguist
// (.ts/.qm): lrelease isn't available on a bare Omarchy install, and
// Quickshell plugins don't get to install a QTranslator into the shell's
// shared QML engine anyway. Instead this is a plain string table keyed by
// language, picked at call time from Qt.locale() - same idea, much less
// machinery, consistent with this project's existing preference for
// avoiding extra runtime dependencies (see HANDOVER.md).
//
// All user-facing chrome text lives here - the one exception is the
// shortcut labels/groups themselves (e.g. "File", "Ctrl+O"), which come
// straight from the target app's own AT-SPI tree and are that app's own
// (possibly already-localized) strings, not this project's to translate.
//
// Known limitation, not fixed here: a couple of templates below embed a
// language-specific grammatical assumption (e.g. French "de" doesn't elide
// to "d'" before a vowel-starting app name; the German "this app" fallback
// is pre-declined for the one preposition it's actually used with;
// Portuguese "de este" should properly contract to "deste"). Real per-app
// grammatical agreement would need a much bigger system than a flat string
// table - not worth it for the handful of sentences here.

var strings = {
  en: {
    daemon_unreachable: "Couldn't reach the kheetsheet daemon — is kheetsheet-hyprd running?",
    no_active_window: "No active window known",
    parse_error: "Couldn't parse the daemon's response",
    reading_shortcuts: "Reading shortcuts…",
    no_shortcuts_found: "No shortcuts found — {app} doesn't expose its menu to the accessibility tree.",
    try_native_overlay: "Try {app}'s own shortcuts overlay",
    this_app: "this app",
    no_shortcuts_to_display: "No shortcuts to display — {reason}",
    ydotool_missing: "ydotool isn't installed — can't send the native shortcut combo",
    refocus_failed: "Couldn't refocus the original window (it may have closed)",
    no_native_overlay: "{app} doesn't seem to have its own shortcuts overlay",
  },
  fr: {
    daemon_unreachable: "Impossible de joindre le démon kheetsheet — kheetsheet-hyprd est-il en cours d'exécution ?",
    no_active_window: "Aucune fenêtre active connue",
    parse_error: "Impossible d'analyser la réponse du démon",
    reading_shortcuts: "Lecture des raccourcis…",
    no_shortcuts_found: "Aucun raccourci trouvé — {app} n'expose pas son menu à l'arbre d'accessibilité.",
    try_native_overlay: "Essayer le propre écran de raccourcis de {app}",
    this_app: "cette application",
    no_shortcuts_to_display: "Aucun raccourci à afficher — {reason}",
    ydotool_missing: "ydotool n'est pas installé — impossible d'envoyer la combinaison de raccourci native",
    refocus_failed: "Impossible de refocaliser la fenêtre d'origine (elle a peut-être été fermée)",
    no_native_overlay: "{app} ne semble pas avoir son propre écran de raccourcis",
  },
  de: {
    daemon_unreachable: "Der kheetsheet-Dienst ist nicht erreichbar — läuft kheetsheet-hyprd?",
    no_active_window: "Kein aktives Fenster bekannt",
    parse_error: "Antwort des Diensts konnte nicht gelesen werden",
    reading_shortcuts: "Tastenkombinationen werden geladen…",
    no_shortcuts_found: "Keine Tastenkombinationen gefunden — {app} stellt sein Menü nicht im Eingabehilfen-Baum bereit.",
    try_native_overlay: "Eigene Tastenkombinationen-Übersicht von {app} versuchen",
    this_app: "dieser App", // pre-declined dative, matches "von {app}" above
    no_shortcuts_to_display: "Keine Tastenkombinationen anzuzeigen — {reason}",
    ydotool_missing: "ydotool ist nicht installiert — die native Tastenkombination kann nicht gesendet werden",
    refocus_failed: "Das ursprüngliche Fenster konnte nicht wieder fokussiert werden (es wurde möglicherweise geschlossen)",
    no_native_overlay: "{app} scheint keine eigene Tastenkombinationen-Übersicht zu haben",
  },
  es: {
    daemon_unreachable: "No se pudo contactar con el demonio de kheetsheet — ¿está en ejecución kheetsheet-hyprd?",
    no_active_window: "No se conoce ninguna ventana activa",
    parse_error: "No se pudo analizar la respuesta del demonio",
    reading_shortcuts: "Leyendo atajos…",
    no_shortcuts_found: "No se encontraron atajos — {app} no expone su menú al árbol de accesibilidad.",
    try_native_overlay: "Probar la propia ventana de atajos de {app}",
    this_app: "esta aplicación",
    no_shortcuts_to_display: "No hay atajos que mostrar — {reason}",
    ydotool_missing: "ydotool no está instalado — no se puede enviar la combinación de teclas nativa",
    refocus_failed: "No se pudo volver a enfocar la ventana original (puede que se haya cerrado)",
    no_native_overlay: "{app} no parece tener su propia ventana de atajos",
  },
  it: {
    daemon_unreachable: "Impossibile raggiungere il demone di kheetsheet — kheetsheet-hyprd è in esecuzione?",
    no_active_window: "Nessuna finestra attiva nota",
    parse_error: "Impossibile analizzare la risposta del demone",
    reading_shortcuts: "Lettura delle scorciatoie…",
    no_shortcuts_found: "Nessuna scorciatoia trovata — {app} non espone il proprio menu all'albero di accessibilità.",
    try_native_overlay: "Prova la finestra delle scorciatoie di {app}",
    this_app: "questa app",
    no_shortcuts_to_display: "Nessuna scorciatoia da mostrare — {reason}",
    ydotool_missing: "ydotool non è installato — impossibile inviare la combinazione di tasti nativa",
    refocus_failed: "Impossibile rimettere a fuoco la finestra originale (potrebbe essere stata chiusa)",
    no_native_overlay: "{app} non sembra avere una propria finestra delle scorciatoie",
  },
  pt_BR: {
    daemon_unreachable: "Não foi possível acessar o daemon do kheetsheet — o kheetsheet-hyprd está em execução?",
    no_active_window: "Nenhuma janela ativa conhecida",
    parse_error: "Não foi possível interpretar a resposta do daemon",
    reading_shortcuts: "Lendo atalhos…",
    no_shortcuts_found: "Nenhum atalho encontrado — o {app} não expõe seu menu para a árvore de acessibilidade.",
    try_native_overlay: "Tentar a própria janela de atalhos de {app}",
    this_app: "este aplicativo",
    no_shortcuts_to_display: "Nenhum atalho para exibir — {reason}",
    ydotool_missing: "o ydotool não está instalado — não é possível enviar a combinação de teclas nativa",
    refocus_failed: "Não foi possível focar novamente a janela original (ela pode ter sido fechada)",
    no_native_overlay: "o {app} não parece ter uma janela de atalhos própria",
  },
  ja: {
    daemon_unreachable: "kheetsheet デーモンに接続できません — kheetsheet-hyprd は実行されていますか?",
    no_active_window: "アクティブなウィンドウが見つかりません",
    parse_error: "デーモンの応答を解析できませんでした",
    reading_shortcuts: "ショートカットを読み込み中…",
    no_shortcuts_found: "ショートカットが見つかりません — {app} はメニューをアクセシビリティツリーに公開していません。",
    try_native_overlay: "{app} 自体のショートカット一覧を試す",
    this_app: "このアプリ",
    no_shortcuts_to_display: "表示できるショートカットがありません — {reason}",
    ydotool_missing: "ydotool がインストールされていません — ネイティブのショートカットキーを送信できません",
    refocus_failed: "元のウィンドウにフォーカスを戻せませんでした(閉じられた可能性があります)",
    no_native_overlay: "{app} には独自のショートカット一覧がないようです",
  },
  zh_Hans: {
    daemon_unreachable: "无法连接到 kheetsheet 守护进程 — kheetsheet-hyprd 是否正在运行?",
    no_active_window: "未检测到活动窗口",
    parse_error: "无法解析守护进程的响应",
    reading_shortcuts: "正在读取快捷键…",
    no_shortcuts_found: "未找到快捷键 — {app} 没有向辅助功能树公开其菜单。",
    try_native_overlay: "尝试 {app} 自带的快捷键面板",
    this_app: "此应用",
    no_shortcuts_to_display: "没有可显示的快捷键 — {reason}",
    ydotool_missing: "未安装 ydotool — 无法发送原生快捷键组合",
    refocus_failed: "无法重新聚焦原始窗口(它可能已关闭)",
    no_native_overlay: "{app} 似乎没有自带的快捷键面板",
  },
  ru: {
    daemon_unreachable: "Не удалось подключиться к службе kheetsheet — запущен ли kheetsheet-hyprd?",
    no_active_window: "Активное окно не определено",
    parse_error: "Не удалось разобрать ответ службы",
    reading_shortcuts: "Загрузка сочетаний клавиш…",
    no_shortcuts_found: "Сочетания клавиш не найдены — {app} не предоставляет своё меню дереву доступности.",
    try_native_overlay: "Показать собственные сочетания клавиш {app}",
    this_app: "этого приложения",
    no_shortcuts_to_display: "Нет сочетаний клавиш для отображения — {reason}",
    ydotool_missing: "ydotool не установлен — не удаётся отправить встроенное сочетание клавиш",
    refocus_failed: "Не удалось вернуть фокус исходному окну (возможно, оно было закрыто)",
    no_native_overlay: "у {app}, похоже, нет собственных сочетаний клавиш",
  },
}

// Qt.locale().name is glibc-style, e.g. "en_US", "fr_FR", "pt_BR", "zh_CN".
// Maps that down to one of the keys in `strings` above, falling back to
// English for anything unsupported (including Chinese variants other than
// Simplified, which this project doesn't have a translation for yet).
function resolveLocale() {
  var name = (typeof Qt !== "undefined" && Qt.locale) ? Qt.locale().name : "en_US"
  var parts = (name || "en_US").split("_")
  var lang = parts[0]
  var region = parts[1] || ""

  if (lang === "pt") return "pt_BR"
  if (lang === "zh") return (region === "CN" || region === "SG") ? "zh_Hans" : "en"
  if (strings[lang] !== undefined) return lang
  return "en"
}

function tr(key, params) {
  var table = strings[resolveLocale()] || strings.en
  var template = table[key] !== undefined ? table[key] : strings.en[key]
  if (template === undefined) return key
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, function (_, k) {
    return params[k] !== undefined ? params[k] : ""
  })
}
