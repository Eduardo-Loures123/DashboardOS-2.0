#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || exit 1
set -a
source /etc/dashboardos/dashboardos.env
set +a
umask 077
cd /opt/dashboardos/current
runuser -u dashboardos --preserve-environment -- .venv/bin/python deployment/aws/backup.py
