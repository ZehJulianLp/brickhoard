#!/bin/bash
set -Eeuo pipefail

DOMAIN=brickhoard.julianverse.de
APP_URL=http://127.0.0.1:54709/
NGINX_CONF=/etc/nginx/nginx.conf
NGINX_DIR=/etc/nginx/conf.d
NGINX_SITE="$NGINX_DIR/brickshelf.conf"
SOURCE_SITE=/home/srvmgr/brickshelf/deploy/nginx-brickshelf.conf
BACKUP="${NGINX_CONF}.bak-brickshelf-$(date +%Y%m%d-%H%M%S)"
SITE_BACKUP="${NGINX_SITE}.bak-brickshelf-$(date +%Y%m%d-%H%M%S)"
SITE_EXISTED=0
CONFIG_CHANGED=0

if [[ $EUID -ne 0 ]]; then
    echo "Bitte als root ausführen: sudo $0" >&2
    exit 1
fi

for command in certbot curl install loginctl nginx sed systemctl; do
    command -v "$command" >/dev/null || {
        echo "Fehlendes Programm: $command" >&2
        exit 1
    }
done

[[ -f "$SOURCE_SITE" ]] || {
    echo "Nginx-Snippet fehlt: $SOURCE_SITE" >&2
    exit 1
}

curl --fail --silent --show-error --max-time 5 "$APP_URL" >/dev/null
nginx -t
loginctl enable-linger srvmgr

[[ -e "$NGINX_SITE" ]] && SITE_EXISTED=1
install -m 0600 "$NGINX_CONF" "$BACKUP"
if (( SITE_EXISTED == 1 )); then
    install -m 0600 "$NGINX_SITE" "$SITE_BACKUP"
fi

restore_nginx() {
    local exit_code=$?

    if (( exit_code != 0 && CONFIG_CHANGED == 1 )); then
        echo "Fehler aufgetreten; stelle die vorherige Nginx-Konfiguration wieder her." >&2
        install -m 0644 "$BACKUP" "$NGINX_CONF"
        if (( SITE_EXISTED == 1 )); then
            install -m 0644 "$SITE_BACKUP" "$NGINX_SITE"
        else
            rm -f "$NGINX_SITE"
        fi
        nginx -t || true
    fi

    systemctl start nginx || true
    exit "$exit_code"
}
trap restore_nginx EXIT INT TERM

echo "Stoppe Nginx für die standalone ACME-Challenge."
systemctl stop nginx

certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --preferred-challenges http \
    --keep-until-expiring \
    -d "$DOMAIN"

CONFIG_CHANGED=1
install -d -m 0755 "$NGINX_DIR"
install -m 0644 "$SOURCE_SITE" "$NGINX_SITE"

if ! grep -Fq 'include /etc/nginx/conf.d/*.conf;' "$NGINX_CONF"; then
    sed -i '/^[[:space:]]*http[[:space:]]*{/a\    include /etc/nginx/conf.d/*.conf;' "$NGINX_CONF"
fi

nginx -t
systemctl start nginx

curl \
    --fail \
    --silent \
    --show-error \
    --max-time 10 \
    --resolve "$DOMAIN:443:127.0.0.1" \
    "https://$DOMAIN/" >/dev/null

CONFIG_CHANGED=0
trap - EXIT INT TERM

echo "BrickHoard ist unter https://$DOMAIN erreichbar."
echo "Nginx-Backup: $BACKUP"
