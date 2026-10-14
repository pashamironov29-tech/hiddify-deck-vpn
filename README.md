# Hiddify VPN toggle for Steam Deck game mode

[![CI](https://github.com/pashamironov29-tech/hiddify-deck-vpn/actions/workflows/ci.yml/badge.svg)](https://github.com/pashamironov29-tech/hiddify-deck-vpn/actions/workflows/ci.yml)

Decky Loader plugin + systemd service that keeps the Hiddify (sing-box) VPN running in **Game Mode** and lets you toggle it from the Quick Access menu («…» → 🔌 → Hiddify).

## Requirements
- Steam Deck (SteamOS 3.x), logged in as the `deck` user, with a sudo password set (`passwd`)
- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader)
- [Hiddify](https://github.com/hiddify/hiddify-app/releases) Linux AppImage, extracted to `~/.local/opt/hiddify` (must contain `HiddifyCli`)

## Install (Desktop Mode)
1. Open Hiddify, add **your own** subscription/key, press Connect once, check it works, then close Hiddify.
2. In Konsole, as `deck` (the installer uses `/home/deck`, not `$HOME`):
```bash
git clone https://github.com/pashamironov29-tech/hiddify-deck-vpn.git
cd hiddify-deck-vpn && ./install.sh
```
3. Switch to Game Mode → «…» → 🔌 → Hiddify.

The installer copies your current Hiddify config to `~/.local/share/hiddify-tun/config.json`, installs `hiddify-tun.service` (autostart on boot) and the Decky plugin. No keys are stored in this repo. Running it again stops the service, refreshes that config, and starts the service again.

## Notes
- Don't connect from the Hiddify window while the service is running — only one can hold `tun0`.
- Changed servers/key in Hiddify? Connect once in the app, close it and re-run `./install.sh`.
- The unit runs as root so it can create `tun0`. The plugin does too (`"flags": ["root"]`).
- Uninstall (as `deck`):
```bash
sudo systemctl disable --now hiddify-tun
sudo rm -rf ~/homebrew/plugins/hiddify-tun /etc/systemd/system/hiddify-tun.service
sudo systemctl daemon-reload
sudo systemctl restart plugin_loader
```
`~/.local/share/hiddify-tun` is left in place because it contains your copied config. Delete it yourself if you want the key gone.

## Tests

No Steam Deck or systemd is required. Backend tests mock `systemctl` and `ip`.

```bash
python -m pip install -r requirements-dev.txt
ruff check plugin tests
pytest
node --test tests/frontend.test.mjs
```

GitHub Actions runs lint, pytest, the frontend checks, and `bash -n` on every push and pull request.

---

## По-русски
Плагин Decky и служба, чтобы VPN Hiddify работал в игровом режиме Steam Deck и включался из меню «…» → 🔌 → Hiddify.

1. Поставь Decky Loader и Hiddify (AppImage распакован в `~/.local/opt/hiddify`).
2. В окне Hiddify добавь свой ключ, нажми «Подключиться», проверь и закрой.
3. В Konsole от пользователя `deck`: `git clone https://github.com/pashamironov29-tech/hiddify-deck-vpn.git && cd hiddify-deck-vpn && ./install.sh`
4. Игровой режим → «…» → 🔌 → Hiddify.

Ключей в репозитории нет — берётся твой собственный конфиг из Hiddify. Как прогнать тесты — в разделе Tests выше.

License: MIT
