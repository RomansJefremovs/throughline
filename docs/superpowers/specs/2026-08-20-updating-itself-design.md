# Updating itself

Date: 2026-08-20
Status: proposed
Supersedes: `2026-08-20-telling-you-a-release-exists-design.md`

## Why

Six releases in three days, and people are testing. Every fix reaches them only
if somebody notices a release exists, downloads an installer, and runs it. At
this rate that is several times a day, per tester, forever.

A notification moves that cost nowhere - it still ends in a manual install. An
updater moves it onto the release pipeline once.

## The claim this corrects

The superseded design argued against an updater on one ground: the installer is
unsigned, so every silent update would end at a SmartScreen warning, making
in-place updates worth little.

**That was wrong, and it was asserted without being tested.** Checked properly:

| | |
|---|---|
| Downloaded programmatically (as the updater does) | no `Zone.Identifier` stream at all |
| Signature | `NotSigned` |
| Run with `/S` from code | exit 0, 2.4s, installed |
| Prompts | none |
| Elevation | none - the shell was not an administrator |

SmartScreen's "Windows protected your PC" dialog is triggered *by*
Mark-of-the-Web. Browsers attach it to downloads; a plain HTTP fetch from code
does not. So it never fires on an update.

**Code signing and auto-update are independent.** Signing removes the warning on
the *first, manual, browser-downloaded* install and nothing else - a one-time
onboarding cost, not a per-update one. Worth buying eventually. Not a blocker
for this.

## Design

Tauri's own updater, which exists for exactly this.

### Signing the package, which is not code signing

`tauri-plugin-updater` refuses a package it cannot verify. The key is a
minisign keypair from `tauri signer generate` - free, unrelated to
Authenticode, and it answers a different question: not "who wrote this
program" but "did this update come from whoever holds the key".

- Private key: `~/.throughline/updater.key`, outside the repo, never committed
- Public key: `plugins.updater.pubkey` in `tauri.conf.json`, which ships in
  every build

**Losing the private key is the one unrecoverable mistake here.** Every
installed client has the matching public key baked in and will refuse anything
signed by a different one. There is no remote revocation and no way to push a
new key - the only recovery is every tester manually installing a build that
carries the new one. It needs a backup somewhere other than this laptop.

The build script checks for the key *before* the five-minute build rather than
after, and its failure message says to restore the original rather than
generate a fresh one.

### The manifest

`createUpdaterArtifacts: true` makes the bundle step emit a `.sig` beside the
installer. The build script then writes `latest.json`:

```json
{
  "version": "0.7.0",
  "pub_date": "...",
  "platforms": {
    "windows-x86_64": { "signature": "...", "url": "https://github.com/.../v0.7.0/..." }
  }
}
```

The endpoint is
`https://github.com/RomansJefremovs/throughline/releases/latest/download/latest.json`.
GitHub resolves `/releases/latest/download/` to whatever the newest release
holds, so the endpoint is a constant and no republishing is needed.

Written by the script rather than by hand: it repeats the version three times
and carries a signature nobody can proofread.

**Both files must be attached to the release.** An installer published without
its manifest is invisible to every client, and nothing fails loudly - they
simply never hear about it. The script prints the `gh release create` line with
both, which is the only guard against getting this wrong.

### In the window

On start, after the project loads and deliberately not awaited - a slow GitHub
must never delay the one screen that has to name an action:

> 0.7.0 is available. **Update and restart** · **Later**

One line, in the existing quiet `sub` style, under the action. Nothing installs
until it is pressed. "Later" hides it for this session.

This bends binding rule 1, which says the front door names exactly one action.
Deliberately: it is one fact about the tool rather than a list of the user's
undone work, in one sentence, dismissed with one word - the same shape rule 5
already permits for a stale input.

### Failure is silence

No network, GitHub down, a manifest not yet published, a rate limit: the line
does not appear and nothing is said. `window.__TAURI__.updater` is absent in a
plain browser, so running the app through `throughline serve` shows nothing
either - normal, not an error.

A tool that complains about not reaching the internet is worse than one that
never looked.

### Restarting

Installing exits the app and `process.relaunch()` brings it back. Agent
consoles are spawned detached with `CREATE_NEW_CONSOLE` precisely so they
outlive the window, so an update never interrupts work in progress. That
property was already load-bearing; this depends on it.

## What this does not do

- **No automatic install.** It asks. A tool that replaced itself under a
  running session would be making a decision that is not its to make.
- **No background polling.** Once per launch, and only at launch.
- **No pre-releases.** `releases/latest` excludes them by definition.
- **No downgrade.** A client newer than the manifest is told nothing.
- **No macOS or Linux.** `windows-x86_64` only, because that is the only thing
  that is built.

## Testing

The updater itself cannot be unit-tested from Python - it is Rust plus a
GitHub round trip - so what gets asserted is what can be:

- The build script fails, before building, when the signing key is missing.
- The build script fails when `createUpdaterArtifacts` has been turned off and
  no `.sig` appears.
- `latest.json` names the same version as the four bump sites, carries the
  signature from disk, and points at the URL the release will actually have.

The rest is verified by doing it: publish, then have an older installed client
find, install and restart into the new one. **That end-to-end check is the only
thing that proves the pubkey, the manifest and the endpoint agree**, and no
amount of unit testing substitutes for it. It has to be run once per key, not
once per release.
