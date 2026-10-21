# Gemelo Digital — Proceso Civil de Nicaragua (CPCN, Ley 908)

Simulación determinista y auditable del juicio ordinario civil: máquina de
estados (YAML), cómputo de plazos con calendario judicial, comandos CQRS por
acto procesal, RBAC Zero Trust sobre JWT y tablero visual React Flow.

```
app/                 Backend FastAPI (dominio + aplicación + API)
frontend-web/        SPA React 18 + TypeScript + Tailwind + @xyflow/react
backend/Dockerfile   Imagen multi-stage Python slim (API)
frontend/Dockerfile  Imagen multi-stage Node alpine -> Nginx alpine (SPA)
docker-compose.yml   Orquestador maestro (db + redis + backend + frontend)
infra/db/init/       Endurecimiento PostgreSQL (auditoría inmutable)
.github/workflows/   CI: pytest+ruff · tsc+eslint · docker build smoke
```

---

## Levantar TODO con un solo comando (Windows 11 + WSL2)

### 1. Prerrequisitos (una sola vez)

1. **Instalar WSL2** (PowerShell como Administrador):
   ```powershell
   wsl --install -d Ubuntu-24.04
   ```
   Reinicia y crea usuario/contraseña de Linux cuando se solicite.

2. **Instalar Docker Desktop para Windows**
   (https://www.docker.com/products/docker-desktop/). En *Settings → Resources →
   WSL Integration*, habilita la integración con **Ubuntu-24.04**. Deja activado
   el motor **WSL 2** (Settings → General → Use the WSL 2 based engine).

3. **Clonar el repo DENTRO del filesystem de Linux** (no en `/mnt/c`, los bind
   mounts cruzados son ~10× más lentos y rompen hot-reload):
   ```bash
   # desde la terminal de Ubuntu (WSL)
   git clone <url-del-repo> ~/gemelo-digital && cd ~/gemelo-digital
   ```

### 2. Configuración local (una sola vez)

```bash
cp .env.example .env
# Editar .env: define POSTGRES_PASSWORD y GEMELO_JWT_SECRET (valores DEMO no sirven en prod).
# Generar un secreto JWT fuerte:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

> `.env` está en `.gitignore`: las credenciales reales jamás se versionan.
> `docker compose` falla con mensaje explícito si falta una variable obligatoria.

### 3. El comando único 🚀

```bash
docker compose up -d --build
```

Construye las imágenes (primera vez ~5 min) y levanta en orden garantizado por
healthchecks: **PostgreSQL → Redis → FastAPI (hot-reload) → Frontend**.

### 4. Verificación

```bash
docker compose ps                      # todo "running (healthy)"
curl http://localhost:${BACKEND_PORT:-8000}/healthz     # {"estado":"ok","dominio":"proceso_civil_nicaragua"}
```

| Servicio            | URL                          | Notas                                   |
|---------------------|------------------------------|-----------------------------------------|
| Tablero del caso    | http://localhost:${FRONTEND_PORT:-3000}        | SPA; proxy interno `/api/*` → backend   |
| API docs (Swagger)  | http://localhost:${BACKEND_PORT:-8000}/docs   | Comandos CQRS + queries + auth          |
| Health API          | http://localhost:${BACKEND_PORT:-8000}/healthz| Usado por el healthcheck del compose    |
| PostgreSQL          | 127.0.0.1:5432               | Solo loopback (no expuesto a la LAN)    |
| Redis               | 127.0.0.1:6379               | Solo loopback                           |

Ruta principal del tablero: `http://localhost:${FRONTEND_PORT:-3000}/caso/<uuid>` (deep-link
resuelto por el fallback SPA de Nginx/Vite).

### 5. Ciclo de desarrollo diario

- Cambias `app/**` o `config/flow_reglas.yaml` → uvicorn **recarga solo** (bind mount + `--reload`).
- Cambias `frontend-web/src/**` → Vite HMR actualiza el navegador.
- Tests (dentro del contenedor, sin instalar nada en Windows):
  ```bash
  docker compose exec backend pytest -q
  docker compose exec backend ruff check app tests
  ```
- Worker de vencimientos (rebeldía/preclusión automáticas, opt-in):
  ```bash
  docker compose --profile workers up -d worker
  ```

### 6. Operaciones habituales

```bash
docker compose logs -f backend         # seguir logs de la API
docker compose restart backend         # reiniciar sin reconstruir
docker compose down                    # apagar (los DATOS persisten en gemelo_pgdata)
docker compose down -v                 # ⚠️ BORRA la base de datos (solo reset total)
docker compose build --no-cache backend  # rebuild limpio tras cambiar requirements.txt
```

### 7. Solución de problemas comunes en WSL2

| Síntoma | Causa probable | Fix |
|---|---|---|
| `docker: command not found` dentro de WSL | WSL integration desactivada | Docker Desktop → Settings → WSL Integration → ON |
| Puerto 3000/8000 ocupado (`address already in use`) | Otro proceso en Windows usa el puerto | Cambia `FRONTEND_PORT`/`BACKEND_PORT` en `.env` |
| Hot-reload no detecta cambios | Repo clonado en `/mnt/c` | Mueve el repo al filesystem Linux (`~/...`) |
| `npm ci` lento en frontend | node_modules sobre bind mount | Ya resuelto: volumen nombrado `gemelo_node_modules` |
| DB vacía tras `down -v` | El init SQL solo corre al crear el volumen | `docker compose up -d` vuelve a ejecutar `infra/db/init/*.sql` |

---

## Seguridad del ecosistema (resumen)

- **Zero Trust**: el frontend nunca envía `actor_id`/rol; el backend extrae la identidad del JWT y valida legitimación procesal contra el dominio (403 si no coincide).
- **Contraseñas**: bcrypt; **JWT**: expiración corta configurable (`GEMELO_JWT_EXPIRE_MINUTES`).
- **Auditoría inmutable**: trigger PG bloquea `UPDATE/DELETE` en `log_auditoria`; roles `gemelo_app` (DML) y `gemelo_audit` (solo lectura) con privilegios mínimos.
- **Aislamiento de red**: db/redis solo escuchan en `127.0.0.1`; tráfico entre servicios por `gemelo_network` interna.
- **Sin secretos versionados**: `.env` fuera de Git; plantillas y valores demo únicamente.

## CI/CD

`.github/workflows/ci.yml` corre en cada push/PR a `main`:
1. **backend-tests** — ruff (PEP 8) + pytest determinista (FakeClock), con servicio PostgreSQL 15-alpine para pruebas de integración.
2. **frontend-lint** — `tsc` estricto + eslint (`--max-warnings 0`) + build de producción.
3. **docker-build** — construye la imagen backend y valida `docker compose config`.

Configura el secret `CI_POSTGRES_PASSWORD` en GitHub (Settings → Secrets and
variables → Actions) antes del primer run.
