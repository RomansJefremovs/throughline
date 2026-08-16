# Understand

> Wrap the running server in a Tauri window; the blocker is toolchain, not design.

The app already runs. What is missing is the shell.

| Needed | State |
|---|---|
| rustup | not installed |
| MSVC build tools | not installed |
| Frontend | done, unchanged by Tauri |
| Sidecar | done, spawned by the shell |

The ticket is really about installing a toolchain, not about writing an app.
