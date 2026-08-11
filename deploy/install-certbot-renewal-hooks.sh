#!/bin/sh
set -eu

SOURCE_DIR=/home/srvmgr/brickshelf/deploy

if [ "$(id -u)" -ne 0 ]; then
    echo "Bitte als root ausführen: sudo $0" >&2
    exit 1
fi

install -D -m 0755 \
    "$SOURCE_DIR/certbot-renewal-pre.sh" \
    /etc/letsencrypt/renewal-hooks/pre/10-stop-nginx
install -D -m 0755 \
    "$SOURCE_DIR/certbot-renewal-post.sh" \
    /etc/letsencrypt/renewal-hooks/post/90-start-nginx

systemctl enable --now certbot-renew.timer

echo "Certbot-Renewal-Hooks sind installiert; certbot-renew.timer ist aktiv."
