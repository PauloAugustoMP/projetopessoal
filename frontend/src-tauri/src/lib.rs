//! Native shell only — all business logic lives in the Python backend
//! (docs/architecture.md §2). The webview talks to it over HTTP/WebSocket.

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .run(tauri::generate_context!())
        .expect("error while running the desktop app");
}
