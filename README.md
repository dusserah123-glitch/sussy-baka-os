# SUSSY BAKA OS

**Sussy Baka OS 0.3.0** is a real KDE Plasma desktop-remix project based on **Kubuntu 26.04.1 LTS**. It is not a browser-based desktop simulation. It uses the distribution's real kernel, system services, desktop shell, file manager, settings app, installer and package databases.

The current deliverable is a buildable desktop-layer package, a self-hostable account API with a Render Blueprint, hardware-evidence scripts, and an ISO remaster pipeline. It is not yet a certified release image: a booted ISO, installer run, and physical-hardware matrix are still required before calling it production-ready.

## Downloads and project files

- `dist/sussy-baka-os_0.3.0_all.deb` — Sussy Baka desktop package.
- `assets/wallpapers/sussy-baka-space-age.png` — original space wallpaper.
- `scripts/build-iso.sh` — remaster the verified official Kubuntu 26.04.1 LTS ISO.
- `scripts/verify-project.sh` — automated source, test, package and archive checks.
- `render.yaml` — Render Blueprint for the Sussy Account API (deployment requires your repository, Render workspace and SMTP credentials).
- `scripts/check-iso-build-host.sh` — validates tools, disk space and the official Kubuntu ISO checksum.
- `scripts/collect-hardware-report.sh` — gathers device/driver inventory on a real test computer.
- `docs/` — build instructions, installer constraints, tests, security and service deployment.

## Implemented components

| App / system component | Real implementation |
|---|---|
| SUS STORE | Custom PyQt6 desktop application. It queries APT's package cache and the configured Flathub remote, checks installed state, and calls APT/Flatpak through `pkexec`. The package manager's real output and exit code determine success. |
| SUSSY ACCOUNT | Desktop client plus a self-hostable FastAPI backend. Includes Argon2id passwords, email verification, password reset, expiring access tokens, rotating refresh tokens, profile color and device/session revocation. |
| SUS AI | Streaming OpenAI-compatible chat UI. API key is stored through Secret Service; no secret is embedded in source or config. |
| Liquid Glass theme | KDE Plasma 6 global theme, desktop theme, translucent Qt app surfaces, KWin blur settings, floating panel artwork, original wallpaper and crew-color palette. Compositor/hardware support affects blur. |
| Welcome | First-login appearance setup that changes real KDE Plasma user preferences. |
| Windows compatibility | Wine/KIO `.exe` integration and optional Bottles package. Application/game compatibility is not guaranteed. |
| Among Us | Genuine Steam install URI for App ID `945360`; user needs a Steam account and the game license. |
| Settings / file manager / updates | Uses native KDE System Settings, Dolphin and Discover/PackageKit. |
| Installer branding | Sussy Baka Calamares branding assets are provided; the original distribution's real partitioning and bootloader modules are retained. |

## Important incomplete items

- **Bootable ISO:** the remaster script is provided, but no image was built in this workspace. The 5 GB official base ISO and xorriso/SquashFS build tools are not available in this network-isolated Debian container.
- **Custom one-screen installer:** not complete. The provided Calamares brand changes its look when used by a Calamares-based image, but does not collapse partitioning, account creation and bootloader configuration into one screen. Do not describe it as complete.
- **Hardware testing:** no physical PC was attached to this build environment. No vendor/model has been certified.
- **Hosted account service:** not operated by this project. The included API must be deployed by the user with SMTP and HTTPS.
- **Cloud sync:** synchronized files/settings and MFA are not implemented.

These limitations are recorded in `docs/FEATURE_MATRIX.md` rather than being hidden behind demo UI.

## Build the desktop package

On a Kubuntu 26.04.1 / compatible KDE Plasma 6 development system:

```bash
./scripts/build-deb.sh
sudo apt install ./dist/sussy-baka-os_0.3.0_all.deb
```

For optional Windows compatibility, Steam and Flathub components:

```bash
sudo ./scripts/install-optional-components.sh
```

Run the user theme setup:

```bash
apply-theme.sh
```

The desktop package requires `python3-pyqt6` for its Qt applications. Use a disposable VM before installing on a production computer.

## Build the ISO

Follow `docs/BUILDING.md` and `docs/INSTALLER.md`. Run `scripts/check-iso-build-host.sh` first. The script accepts the official `kubuntu-26.04.1-desktop-amd64.iso`, verifies the official SHA-256, adds the desktop package into its live SquashFS, preserves original boot metadata and emits a SHA-256 sidecar.

```bash
sudo ./scripts/build-iso.sh /path/to/kubuntu-26.04.1-desktop-amd64.iso
```

Then use `scripts/test-iso-qemu.sh` on a host with QEMU. Physical hardware testing is still mandatory before public release.

## Run tests

Development/test requirements are in `tests/requirements.txt`.

```bash
python3 -m pip install -r tests/requirements.txt
./scripts/verify-project.sh
```

The automated tests cover package metadata/command validation and account API flows. They do not test Qt rendering, actual APT/Flatpak transactions against the target repositories, ISO boot, physical hardware, or game compatibility.

## Sussy Account development

Read `docs/ACCOUNT_SERVICE.md` for local development and `docs/CLOUD_DEPLOYMENT.md` for the Render cloud deployment route. For local-only API testing:

```bash
cd services/sussy-account
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export SUSSY_ACCOUNT_SECRET="$(openssl rand -hex 32)"
export SUSSY_ACCOUNT_DB="$PWD/dev-accounts.sqlite3"
export SUSSY_ACCOUNT_DEV_MODE=true
uvicorn app:app --host 127.0.0.1 --port 8080
```

Development mode exposes one-time verification/reset tokens in API responses. Never run it on a public service. Production requires SMTP, HTTPS reverse proxy, backup/monitoring and a unique secret.

## License and trademarks

The project code and original artwork are licensed as described in `LICENSE` and asset notices. Among Us is a trademark of its respective owner; this project is unofficial and does not bundle its copyrighted game assets or executable.
