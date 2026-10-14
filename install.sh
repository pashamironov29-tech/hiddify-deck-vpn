#!/bin/bash
# Установка VPN-службы Hiddify и плагина Decky для игрового режима.
# Перед запуском: Hiddify распакован в ~/.local/opt/hiddify (есть HiddifyCli),
# в окне Hiddify добавлен свой ключ и хотя бы раз нажато «Подключиться».
# Запускать от пользователя deck: пути зашиты как /home/deck.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
DECK_HOME=/home/deck
CFG="$DECK_HOME/.local/share/app.hiddify.com/data/current-config.json"
PLUGIN_DST="$DECK_HOME/homebrew/plugins/hiddify-tun"

[ -x "$DECK_HOME/.local/opt/hiddify/HiddifyCli" ] || { echo "Нет ~/.local/opt/hiddify/HiddifyCli — сначала поставь Hiddify"; exit 1; }
[ -f "$CFG" ] || { echo "Нет конфига. Открой Hiddify, добавь ключ, нажми Подключиться, потом закрой"; exit 1; }
[ -d "$DECK_HOME/homebrew/plugins" ] || { echo "Нет Decky Loader — сначала поставь его"; exit 1; }

# Stop a previous unit before replacing files. Restart=on-failure would
# otherwise respawn HiddifyCli in the middle of the copy.
if [ -f /etc/systemd/system/hiddify-tun.service ]; then
  sudo systemctl stop hiddify-tun || true
fi
# Release tun0 if the desktop app still holds it. pkill returns before the
# process has actually exited, so wait briefly for the config write to finish.
pkill -f HiddifyCli || true
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! pgrep -f HiddifyCli >/dev/null; then
    break
  fi
  sleep 0.3
done
if pgrep -f HiddifyCli >/dev/null; then
  echo "HiddifyCli всё ещё запущен — tun0 может быть занят" >&2
fi

mkdir -p "$DECK_HOME/.local/share/hiddify-tun"
cp "$CFG" "$DECK_HOME/.local/share/hiddify-tun/config.json"
cp "$D/run.sh" "$DECK_HOME/.local/share/hiddify-tun/run.sh"
chmod +x "$DECK_HOME/.local/share/hiddify-tun/run.sh"

sudo cp "$D/hiddify-tun.service" /etc/systemd/system/hiddify-tun.service
sudo rm -rf "$PLUGIN_DST"
sudo mkdir -p "$PLUGIN_DST/dist"
sudo cp "$D/plugin/main.py" "$D/plugin/plugin.json" "$PLUGIN_DST/"
sudo cp "$D/plugin/dist/index.js" "$PLUGIN_DST/dist/index.js"
sudo systemctl daemon-reload
sudo systemctl reset-failed hiddify-tun || true
sudo systemctl enable --now hiddify-tun
sudo systemctl restart plugin_loader
echo "Готово. В игровом режиме: «…» → розетка → Hiddify."
