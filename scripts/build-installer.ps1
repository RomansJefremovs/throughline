# Build the self-contained Windows installer.
#
# Two steps, in this order. PyInstaller freezes the CLI into one exe that
# carries its own Python and the app assets; Tauri then bundles that exe
# beside the desktop shell as an `externalBin` sidecar. The result installs
# and runs on a machine with no Python on it.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$triple = "x86_64-pc-windows-msvc"
$binaries = Join-Path $root "desktop\binaries"

# Tauri names the bundle after the version in its own config, so read it
# from there rather than repeating it here. A hardcoded copy goes stale on
# the next bump and the build "succeeds" with nothing to hand over.
$version = (Get-Content (Join-Path $root "desktop\tauri.conf.json") -Raw |
    ConvertFrom-Json).version

# Find an interpreter that can actually run PyInstaller.
#
# Bare `python` is not good enough on Windows: the Store alias in
# %LOCALAPPDATA%\Microsoft\WindowsApps answers to the name, exits without
# doing anything, and the build then fails with "PyInstaller failed" -
# which sends you looking at PyInstaller rather than at PATH.
#
# The repo's own venv is preferred because it is where the dev extra
# installs PyInstaller in the first place.
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "no interpreter with PyInstaller. Tried '$python'. Run: python -m pip install -e `".[dev]`""
}
Write-Host "==> using $((& $python -c 'import sys; print(sys.executable)'))" -ForegroundColor DarkGray

Write-Host "==> freezing the sidecar" -ForegroundColor Cyan

# --add-data is resolved relative to --specpath, so the source path is
# absolute. A relative one silently resolves inside build/ and fails.
& $python -m PyInstaller `
    --onefile --clean --noconfirm `
    --name throughline `
    --paths (Join-Path $root "src") `
    --add-data "$(Join-Path $root 'src\throughline\app');throughline/app" `
    --add-data "$(Join-Path $root 'skills\throughline');throughline/skill" `
    --distpath (Join-Path $root "build\sidecar\dist") `
    --workpath (Join-Path $root "build\sidecar\work") `
    --specpath (Join-Path $root "build\sidecar") `
    (Join-Path $root "src\throughline\__main__.py")

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Tauri finds the sidecar by target triple and strips the suffix when it
# installs it, so the name has to match the triple exactly.
New-Item -ItemType Directory $binaries -Force | Out-Null
Copy-Item (Join-Path $root "build\sidecar\dist\throughline.exe") `
    (Join-Path $binaries "throughline-$triple.exe") -Force

Write-Host "==> bundling the app" -ForegroundColor Cyan

# The updater will not accept an unsigned package, so the key has to be
# found before a five-minute build rather than after it. This is update
# signing, not code signing - it proves the package came from whoever
# holds this key, and has nothing to do with SmartScreen.
$keyPath = Join-Path $env:USERPROFILE ".throughline\updater.key"
if (-not (Test-Path $keyPath)) {
    throw @"
no updater signing key at $keyPath

Generate one:
  npx --yes @tauri-apps/cli@^2 signer generate --ci -w "$keyPath"

Then put the public half in desktop\tauri.conf.json under plugins.updater.pubkey.
A different key than the one already published means installed clients will
refuse every update, so restore the original from backup rather than making
a new one.
"@
}
$env:TAURI_SIGNING_PRIVATE_KEY = Get-Content $keyPath -Raw

$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
Push-Location (Join-Path $root "desktop")
try {
    npx --yes @tauri-apps/cli@^2 build
    if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }
}
finally {
    Pop-Location
}

$installer = Join-Path $root `
    "desktop\target\release\bundle\nsis\Throughline_${version}_x64-setup.exe"
if (-not (Test-Path $installer)) { throw "no installer at $installer" }

# The manifest the installed clients poll. It is published as a release
# asset called latest.json, and the endpoint in tauri.conf.json points at
# /releases/latest/download/latest.json - which GitHub always resolves to
# the newest release, so the endpoint itself never changes.
#
# Written here rather than by hand because it repeats the version three
# times and carries a signature nobody can eyeball.
Write-Host "==> writing the update manifest" -ForegroundColor Cyan
$sigPath = "$installer.sig"
if (-not (Test-Path $sigPath)) {
    throw "no signature at $sigPath - is createUpdaterArtifacts still true in tauri.conf.json?"
}
$manifest = Join-Path (Split-Path $installer -Parent) "latest.json"
@{
    version   = $version
    pub_date  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    platforms = @{
        "windows-x86_64" = @{
            signature = (Get-Content $sigPath -Raw).Trim()
            url       = "https://github.com/RomansJefremovs/throughline/releases/download/v$version/$(Split-Path $installer -Leaf)"
        }
    }
} | ConvertTo-Json -Depth 5 | Set-Content $manifest -Encoding utf8

Write-Host "==> $installer" -ForegroundColor Green
Get-Item $installer, $sigPath, $manifest | Select-Object Name, Length

Write-Host @"

Publish BOTH the installer and latest.json, or clients will not see it:
  gh release create v$version "$installer" "$manifest" --title ... --notes-file ...
"@ -ForegroundColor DarkGray
