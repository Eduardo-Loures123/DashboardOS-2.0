#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Execute com sudo"; exit 1; }
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx rsync
id dashboardos >/dev/null 2>&1 || useradd --system --home /var/lib/dashboardos --shell /usr/sbin/nologin dashboardos
install -d -o root -g root -m 755 /opt/dashboardos/releases
install -d -o root -g root -m 700 /etc/dashboardos
install -d -o dashboardos -g www-data -m 750 /var/lib/dashboardos/{excel,auth,backups}
