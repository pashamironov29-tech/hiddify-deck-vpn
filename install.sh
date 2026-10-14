#!/bin/bash
# Установка VPN-службы Hiddify и плагина Decky для игрового режима.
# Перед запуском: Hiddify распакован в ~/.local/opt/hiddify (есть HiddifyCli),
# в окне Hiddify добавлен свой ключ и хотя бы раз нажато «Подключиться».
set -e
D="$(cd "$(dirname "$0")" && pwd)"
CFG=/home/deck/.local/share/app.hiddify.com/data/current-config.json
[ -x /home/deck/.local/opt/hiddify/HiddifyCli ] || { echo "Нет ~/.local/opt/hiddify/HiddifyCli — сначала поставь Hiddify"; exit 1; }
[ -f "$CFG" ] || { echo "Нет конфига. Открой Hiddify, добавь ключ, нажми Подключиться, потом закрой"; exit 1; }
[ -d /home/deck/homebrew/plugins ] || { echo "Нет Decky Loader — сначала поставь его"; exit 1; }
mkdir -p /home/deck/.local/share/hiddify-tun
cp "$CFG" /home/deck/.local/share/hiddify-tun/config.json
cp "$D/run.sh" /home/deck/.local/share/hiddify-tun/run.sh
chmod +x /home/deck/.local/share/hiddify-tun/run.sh
pkill -f HiddifyCli || true
sudo cp "$D/hiddify-tun.service" /etc/systemd/system/
sudo rm -rf /home/deck/homebrew/plugins/hiddify-tun
sudo cp -r "$D/plugin" /home/deck/homebrew/plugins/hiddify-tun
sudo systemctl daemon-reload
sudo systemctl enable --now hiddify-tun
sudo systemctl restart plugin_loader
echo "Готово. В игровом режиме: «…» → розетка → Hiddify."
