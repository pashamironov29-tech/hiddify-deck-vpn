#!/bin/bash
# Start the already-built sing-box config. srun does not rebuild it.
set -euo pipefail
cd /home/deck/.local/opt/hiddify
export LD_LIBRARY_PATH="/home/deck/.local/opt/hiddify/lib:/home/deck/.local/opt/hiddify/usr/lib"
exec ./HiddifyCli srun \
  -D /home/deck/.local/share/hiddify-tun \
  -c /home/deck/.local/share/hiddify-tun/config.json
