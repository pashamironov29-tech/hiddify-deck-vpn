# Hiddify VPN toggle for Steam Deck game mode

Decky Loader plugin + systemd service that keeps the Hiddify (sing-box) VPN running in **Game Mode** and lets you toggle it from the Quick Access menu («…» → 🔌 → Hiddify).

## Requirements
- Steam Deck (SteamOS 3.x) with a sudo password set (`passwd`)
- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader)
- [Hiddify](https://github.com/hiddify/hiddify-app/releases) Linux AppImage, extracted to `~/.local/opt/hiddify` (must contain `HiddifyCli`)

## Install (Desktop Mode)
1. Open Hiddify, add **your own** subscription/key, press Connect once, check it works, then close Hiddify.
2. Run:
```bash
git clone https://github.com/pashamironov29-tech/hiddify-deck-vpn.git
cd hiddify-deck-vpn && ./install.sh
```
3. Switch to Game Mode → «…» → 🔌 → Hiddify.

The installer copies your current Hiddify config to `~/.local/share/hiddify-tun/config.json`, installs `hiddify-tun.service` (autostart on boot) and the Decky plugin. No keys are stored in this repo.

## Notes
- Don't connect from the Hiddify window while the service is running — only one can hold `tun0`.
- Changed servers/key in Hiddify? Connect once in the app, close it and re-run `./install.sh`.
- Uninstall: `sudo systemctl disable --now hiddify-tun && sudo rm -rf ~/homebrew/plugins/hiddify-tun /etc/systemd/system/hiddify-tun.service && sudo systemctl restart plugin_loader`

---

## По-русски
Плагин Decky и служба, чтобы VPN Hiddify работал в игровом режиме Steam Deck и включался из меню «…» → 🔌 → Hiddify.

1. Поставь Decky Loader и Hiddify (AppImage распакован в `~/.local/opt/hiddify`).
2. В окне Hiddify добавь свой ключ, нажми «Подключиться», проверь и закрой.
3. В Konsole: `git clone https://github.com/pashamironov29-tech/hiddify-deck-vpn.git && cd hiddify-deck-vpn && ./install.sh`
4. Игровой режим → «…» → 🔌 → Hiddify.

Ключей в репозитории нет — берётся твой собственный конфиг из Hiddify.

License: MIT
