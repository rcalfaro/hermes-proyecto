#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — decide el modo de arranque de la API según GEMELO_ENV.
#
#   GEMELO_ENV=development  -> uvicorn con --reload (hot-reload) montando el
#                              código desde el host (bind mount en compose).
#   GEMELO_ENV=production   -> uvicorn sin reload, workers limitados.
#
# Se mantiene minúsculo y sin lógica de negocio: la configuración vive en
# variables de entorno (.env -> docker-compose), no en este script.
# =============================================================================
set -euo pipefail

if [[ "${GEMELO_ENV:-production}" == "development" ]]; then
    echo "[entrypoint] modo DESARROLLO: hot-reload activado (watchdog)"
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        --reload-dir /srv/gemelo/app \
        --reload-dir /srv/gemelo/config
fi

echo "[entrypoint] modo PRODUCCIÓN: sin hot-reload"
exec "$@"
