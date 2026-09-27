#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" =~ ^[0-9]+$ ]] || { echo 'Expected numeric task ID' >&2; exit 2; }

image='copromem-shopping-admin-pilot:local'
name='copromem_pilot_site'
expected='sha256:dc591591dec25c52e7648ac45ca643805e4465e72cbe31b648e9953a55cbaa63'
actual="$(docker image inspect "$image" --format '{{.Id}}')"
[[ "$actual" == "$expected" ]] || { echo 'Pilot snapshot image changed' >&2; exit 1; }

docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" -p 127.0.0.1:7780:80 "$image" >/dev/null

ready=0
for _ in {1..30}; do
    if docker exec "$name" sh -lc 'test -S /var/run/mysqld/mysqld.sock' >/dev/null 2>&1 \
        && curl -fsSI --max-time 5 http://127.0.0.1:7780/admin >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done
[[ "$ready" == 1 ]] || { echo 'Shopping Admin did not start' >&2; exit 1; }

docker exec "$name" sh -lc 'cd /var/www/magento2 && php bin/magento cache:flush >/dev/null' >/dev/null
status="$(curl -sSI --max-time 20 http://127.0.0.1:7780/admin | sed -n '1p')"
[[ "$status" == *'200 OK'* ]] || { echo "Unexpected admin response: $status" >&2; exit 1; }

# The image contains the complete Magento filesystem and database snapshot and
# has no external volumes. Container creation options are fixed above.
printf '%s' "$actual|127.0.0.1:7780:80" | sha256sum | cut -d' ' -f1
