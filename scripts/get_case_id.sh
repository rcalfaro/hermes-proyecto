#!/usr/bin/env bash
# Imprime el UUID del expediente demo directamente desde el contenedor PostgreSQL.
docker compose exec -T db psql -U "${POSTGRES_USER:-gemelo_dev}" -d "${POSTGRES_DB:-gemelo_civil}" \
  -At -c "SELECT id FROM caso ORDER BY created_at DESC LIMIT 1;"
