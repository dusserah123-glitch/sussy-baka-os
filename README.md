# SUSSY BAKA OS

**Sussy Baka OS 0.3.0** is a KDE Plasma desktop-remix project based on Kubuntu 26.04.1 LTS. It aims to use a real Linux kernel, KDE desktop shell, native settings, system package manager and real installed applications—not a browser simulation.

## Project status

The GitHub repository currently contains the Sussy Account API, its Docker/Compose setup, Render Blueprint, workflow checks, and this project overview. The full desktop-remix source tree and build outputs are available separately in the project downloads shared with this repository owner; they have **not yet been mirrored into this GitHub repository**. Do not assume the desktop apps or ISO are downloadable from the GitHub file list.

The project source and package checks were run locally: 16 tests passed, Python/shell syntax checks passed, and the Debian package built successfully. GitHub Actions has also successfully validated the published Account API Python files and built its Docker image.

## Planned / implemented desktop components

| Component | Current implementation / constraint |
|---|---|
| SUS STORE | PyQt6 UI integrated with APT and Flatpak package databases; package operations are executed by the real system package managers. |
| SUSSY ACCOUNT | FastAPI backend with Argon2id password hashing, email verification, password reset, JWT access tokens, rotating refresh tokens, device/session revocation and profile fields. The API source is in this repository under `services/sussy-account/`. |
| SUS AI | Streaming UI for OpenAI-compatible APIs. Requires the user's own API endpoint/key. |
| Liquid Glass theme | KDE Plasma 6 theme elements, translucent surfaces, blur settings and crew-color palette. Blur depends on compositor/hardware support. |
| Welcome | First-login setup for real KDE Plasma preferences. |
| Windows compatibility | Wine/KIO integration and optional Bottles package. Individual Windows app/game compatibility is not guaranteed. |
| Among Us | Steam install URI for App ID `945360`; users need their own Steam account and game license. |
| System settings | Uses native KDE System Settings, Dolphin and Discover/PackageKit. |
| Installer | Calamares branding assets exist. A custom one-screen installer is **not implemented**. |

## Release blockers

- **Bootable ISO:** only a remaster script exists; no ISO has been built or boot-tested.
- **One-screen installer:** not implemented. Branding assets do not change the underlying multi-step installer flow.
- **VM installation:** not yet tested in QEMU.
- **Physical hardware:** no computer has been certified.
- **Hosted Sussy Account:** the Render Blueprint is in this repository, but no Render service has been provisioned. The first Render plan was blocked by missing payment information.
- **Cloud sync/MFA:** not implemented.

## Sussy Account API

The service source and deployment files are in `services/sussy-account/`. To run locally, install dependencies, set a random secret and configure SMTP:

```bash
cd services/sussy-account
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SUSSY_ACCOUNT_SECRET="$(openssl rand -hex 32)"
export SUSSY_ACCOUNT_DB="$PWD/dev-accounts.sqlite3"
export SUSSY_ACCOUNT_DEV_MODE=true
uvicorn app:app --host 127.0.0.1 --port 8080
```

Development mode exposes verification/reset tokens in API responses. Never enable it on a public service. Production requires SMTP, HTTPS, backups, monitoring and a unique secret.

## Render deployment

`render.yaml` describes a Docker web service in Singapore with a 10 GB persistent disk. Creating a Render Blueprint did not provision any resources: planning returned `need_payment_info`. After payment details are added, re-plan the Blueprint and review the actual resource plan and charges before approving it. Configure SMTP variables in the Render dashboard; never commit SMTP credentials.

The current design uses SQLite on a persistent disk and is intended to be a single service instance, not horizontally scaled.

## Local project build and testing

The full desktop source/package download is provided separately to the project owner in this ChatGPT conversation. It is not yet mirrored to this GitHub repository. Once extracted, refer to `docs/BUILDING.md`, `docs/INSTALLER.md` and `docs/TESTING.md`.

The project is unofficial. Among Us is a trademark of its respective owner; this project does not bundle the copyrighted game or executable.
