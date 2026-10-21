# =============================================================================
# backend/Dockerfile — API FastAPI del Gemelo Digital (Proceso Civil, Ley 908)
#
# Estrategia: multi-stage para que la imagen final NO contenga herramientas de
# compilación ni cachés de pip (tamaño mínimo, superficie de ataque mínima).
# Imagen base "slim" porque psycopg se instala como wheel binario (no requiere
# gcc/libpq-dev en runtime).
#
# Uso local (con hot-reload):  docker compose up backend   (ver entrypoint.sh)
# Uso producción:              docker build -t gemelo-backend ./backend
# =============================================================================

# ---------------------------------------------------------------------------
# ETAPA 1 · builder — instala dependencias en un venv aislado
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# PYTHONUNBUFFERED: logs inmediatos (crítico para `docker logs` y CI).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Copiamos SOLO los manifiestos primero: así la capa de dependencias queda
# cacheada por Docker y no se reinstala al cambiar código fuente.
COPY requirements.txt requirements-dev.txt ./

# Instala TODAS las dependencias (incluye dev: pytest/ruff) en un venv.
# El entrypoint decide en runtime si usa el modo desarrollo o recorta a prod.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements-dev.txt

# ---------------------------------------------------------------------------
# ETAPA 2 · runtime — imagen final delgada, usuario no-root
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Variables de entorno mínimas; LOS VALORES REALES (secretos, DSN) llegan
# SIEMPRE desde docker-compose/.env — nunca se hardcodean aquí.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    GEMELO_ENV=production \
    GEMELO_HOT_RELOAD=false

# Paquetes mínimos de runtime:
#  - curl: healthcheck del compose (sin él, `depends_on: service_healthy` falla)
#  - libpq5: dependencia dinámica de psycopg si se compila contra libpq
#  - tini (init): reapila procesos huérfanos y propaga SIGTERM → shutdown limpio
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 tini \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root por defensa en profundidad (Zero Trust también aplica al OS).
RUN groupadd --gid 1001 gemelo \
    && useradd --uid 1001 --gid gemelo --shell /usr/sbin/nologin --create-home gemelo

# Venv con dependencias traído de la etapa builder.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv/gemelo

# Código de la aplicación y reglas del motor de estados (YAML determinista).
# La ruta config/ debe existir dentro del contenedor: CaseFlowEngine.desde_yaml()
# resuelve Path(__file__).parents[2] / "config" / "flow_reglas.yaml".
COPY app ./app
COPY config ./config
COPY pytest.ini ./

# En PRODUCCIÓN se elimina todo rastro de dependencias de desarrollo para
# reducir superficie de ataque (pytest/ruff no deben existir en runtime).
# El modo desarrollo del compose monta el código y conserva el venv completo.
COPY entrypoint.sh /entrypoint.sh

# Permisos estrictos: el dueño es root, el proceso solo lee/ejecuta.
RUN chmod +x /entrypoint.sh \
    && chown -R gemelo:gemelo /srv/gemelo

USER gemelo

EXPOSE 8000

# init=dumb: tini como PID 1 (reaping + señales); el CMD puede sobreescribirse
# desde docker-compose para activar el hot-reload en desarrollo.
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
