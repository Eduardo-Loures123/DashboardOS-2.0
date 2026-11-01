#!/usr/bin/env bash
set -euo pipefail
set -a
source /etc/dashboardos/dashboardos.env
set +a
host=${DASHBOARD_ALLOWED_HOSTS%%,*}
for attempt in {1..20}; do
    if curl --fail --silent --unix-socket /run/dashboardos/app.sock -H "Host: $host" -H 'X-Forwarded-Proto: https' http://localhost/login >/dev/null; then
        systemctl is-active --quiet dashboardos
        echo "Gunicorn e login OK; valide HTTPS externo separadamente."
        exit 0
    fi
    sleep 1
done
exit 1
