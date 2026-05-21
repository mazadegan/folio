#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;

#[tauri::command]
fn run_folio(args: Vec<String>) -> Result<String, String> {
    let output = Command::new("folio")
        .args(args)
        .output()
        .map_err(|e| format!("failed to run folio: {e}"))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![run_folio])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
