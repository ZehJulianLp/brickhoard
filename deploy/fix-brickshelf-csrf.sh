#!/bin/sh
set -eu

SOURCE=/home/srvmgr/brickshelf/deploy/nginx-brickshelf.conf
TARGET=/etc/nginx/conf.d/brickshelf.conf
BACKUP="${TARGET}.bak-csrf"

if [ "$(id -u)" -ne 0 ]; then
    echo "Bitte als root ausführen: sudo $0" >&2
    exit 1
fi

install -m 0600 "$TARGET" "$BACKUP"
install -m 0644 "$SOURCE" "$TARGET"

if ! nginx -t; then
    install -m 0644 "$BACKUP" "$TARGET"
    nginx -t
    echo "Nginx-Konfiguration wurde zurückgerollt." >&2
    exit 1
fi

systemctl reload nginx
echo "BrickHoard-CSRF-Fix ist aktiv."
