// The desktop shell. Deliberately thin.
//
// Every rule lives in the Python sidecar, which already has a test suite
// behind it. This process opens a window, starts that sidecar, and points
// the window at it. If a rule ever appears in this file, it has been
// implemented twice and one copy will drift.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::error::Error;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};

/// The sidecar process, kept so it can be stopped when the window closes.
struct Sidecar(Mutex<Option<Child>>);

fn fail(message: impl Into<String>) -> Box<dyn Error> {
    Box::<dyn Error>::from(message.into())
}

/// Start `throughline serve` and learn which port it actually bound.
///
/// Port 0 asks the operating system for any free port, and the sidecar
/// prints the one it got. A fixed port is how a stale server ends up
/// quietly serving old code while the new one fails to bind - which looks
/// exactly like the app being broken, and has cost real hours before.
fn start_sidecar() -> Result<(Child, String), Box<dyn Error>> {
    let mut child = Command::new("throughline")
        .args(["serve", "--port", "0"])
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|e| fail(format!("could not start the throughline sidecar: {e}")))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| fail("the sidecar produced no output"))?;

    let mut line = String::new();
    BufReader::new(stdout)
        .read_line(&mut line)
        .map_err(|e| fail(format!("could not read the sidecar's port: {e}")))?;

    // "Throughline on http://127.0.0.1:53124"
    let url = line
        .split_whitespace()
        .last()
        .filter(|candidate| candidate.starts_with("http"))
        .ok_or_else(|| fail(format!("the sidecar did not report a url: {}", line.trim())))?
        .to_string();

    Ok((child, url))
}

/// Show why the app could not start, instead of vanishing.
///
/// The release build has no console, so a failed sidecar would otherwise
/// close the window with nothing said. A tool that fails silently costs
/// far more time than one that fails loudly.
fn show_failure(app: &tauri::AppHandle, message: &str) -> Result<(), Box<dyn Error>> {
    let escaped = message.replace('\\', "\\\\").replace('"', "\\\"");
    WebviewWindowBuilder::new(app, "error", WebviewUrl::App("error.html".into()))
        .title("Throughline could not start")
        .inner_size(720.0, 620.0)
        .initialization_script(&format!("window.__THROUGHLINE_ERROR__ = \"{escaped}\";"))
        .build()?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let (child, url) = match start_sidecar() {
                Ok(started) => started,
                Err(problem) => {
                    show_failure(app.handle(), &problem.to_string())?;
                    return Ok(());
                }
            };
            app.manage(Sidecar(Mutex::new(Some(child))));

            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse()?))
                .title("Throughline")
                .inner_size(1180.0, 800.0)
                .min_inner_size(720.0, 520.0)
                .build()?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // The sidecar belongs to this window. Leaving it running would
            // hold a port and confuse the next launch.
            if matches!(event, WindowEvent::Destroyed) {
                if let Some(sidecar) = window.app_handle().try_state::<Sidecar>() {
                    if let Ok(mut held) = sidecar.0.lock() {
                        if let Some(mut child) = held.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("Throughline failed to start");
}
