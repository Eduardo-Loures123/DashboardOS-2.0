#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && $# -eq 1 ]] || { echo "Uso: sudo bash deploy.sh DIRETORIO_FONTE"; exit 1; }
source_dir=$(realpath "$1")
[[ -f "$source_dir/app.py" && -f /etc/dashboardos/dashboardos.env ]] || exit 1
[[ -f /var/lib/dashboardos/excel/dados_dashboard.xlsx && -f /var/lib/dashboardos/auth/auth.sqlite3 ]] || { echo "Importe os dados existentes primeiro"; exit 1; }
release=/opt/dashboardos/releases/$(date -u +%Y%m%dT%H%M%S)_$$
install -d -m 755 "$release"
rsync -a --exclude='.venv' --exclude='dados' --exclude='instance' --exclude='.env*' --exclude='.git' --exclude='node_modules' --exclude='__pycache__' "$source_dir/" "$release/"
python3 -m venv "$release/.venv"
"$release/.venv/bin/pip" install -r "$release/deployment/aws/requirements.txt"
"$release/.venv/bin/pip" freeze > "$release/installed-requirements.txt"
set -a
source /etc/dashboardos/dashboardos.env
set +a
(cd "$release" && runuser -u dashboardos --preserve-environment -- .venv/bin/python -c 'from app import app; app.config["STORE"].read(); print("Configuração e Excel OK")')
previous=$(readlink -f /opt/dashboardos/current || true)
if [[ -n "$previous" ]]; then bash "$previous/deployment/aws/backup.sh"; fi
install -m 644 "$release/deployment/aws/dashboardos.service" /etc/systemd/system/dashboardos.service
ln -s "$release" /opt/dashboardos/current.next
mv -Tf /opt/dashboardos/current.next /opt/dashboardos/current
systemctl daemon-reload
systemctl enable dashboardos
systemctl restart dashboardos
if ! bash "$release/deployment/aws/check.sh"; then
    if [[ -n "$previous" ]]; then
        ln -s "$previous" /opt/dashboardos/current.rollback
        mv -Tf /opt/dashboardos/current.rollback /opt/dashboardos/current
        systemctl restart dashboardos
    fi
    echo "Falha na verificação; consulte journalctl -u dashboardos" >&2
    exit 1
fi
