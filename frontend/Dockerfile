# =============================================================================
# frontend/Dockerfile — Tablero visual del Gemelo Digital (React Flow)
#
# El proyecto de este repositorio es una SPA Vite + React 18 + TS estricto
# (frontend-web/). La imagen replica el patrón Next.js App Router solicitado:
# build determinista en Node alpine y runtime Nginx alpine con SPA fallback,
# sin Node ni toolchain en la imagen final (tamaño ~40 MB vs ~900 MB).
#
# Producción:      docker build -t gemelo-frontend ./frontend
# Desarrollo:      compose usa el servicio `frontend` con hot-reload de Vite.
# =============================================================================

# ---------------------------------------------------------------------------
# ETAPA 1 · deps — instala node_modules con caché eficiente
# ---------------------------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /build

# Copiamos solo los manifiestos: si package-lock no cambia, Docker reutiliza
# esta capa completa (npm ci puede tardar minutos; cachearla es crítico).
COPY package.json package-lock.json ./

# npm ci = instalación reproducible anclada al lockfile (determinismo == CI).
# --omit=dev se omite a propósito: vite/tsc son necesarios en la etapa build.
RUN npm ci --no-audit --no-fund

# ---------------------------------------------------------------------------
# ETAPA 2 · build — compila TypeScript y genera dist/ estático
# ---------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /build

COPY --from=deps /build/node_modules ./node_modules
COPY . .

# API pública del backend que consume el navegador. En compose se inyecta
# "" (string vacío) para usar rutas relativas /api/* servidas por el proxy
# interno de Vite/Nginx — así no hay CORS ni URLs quemadas.
ARG GEMELO_API_BASE_URL=""
ENV GEMELO_API_BASE_URL=${GEMELO_API_BASE_URL} \
    NODE_ENV=production

# typecheck (tsc --noEmit implícito en `tsc -b`) + bundle de producción.
# Si el tipado estricto falla, el build FAILA: la UI nunca se publica rota.
RUN npm run build

# ---------------------------------------------------------------------------
# ETAPA 3 · runtime — Nginx alpine sirviendo solo artefactos estáticos
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Config SPA: try_files -> index.html (permite deep links como /caso/{id})
# + proxy inverso /api -> backend:8000 (origen único: simplifica cookies JWT
#   SameSite=Strict y elimina CORS del ecosistema local).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Artefactos compilados: nada de node_modules ni fuentes en producción.
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 3000

# Healthcheck ligero con wget ya presente en busybox (evita instalar curl).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:3000/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
