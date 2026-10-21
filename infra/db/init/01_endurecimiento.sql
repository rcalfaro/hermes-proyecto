-- =============================================================================
-- infra/db/init/01_endurecimiento.sql — endurecimiento de seguridad PostgreSQL
-- Ejecutado automáticamente por el entrypoint de postgres AL INICIALIZAR el
-- volumen gemelo_pgdata (solo primera vez; borrar el volumen para rejugarlo).
--
-- Principios aplicados:
--   * Inmutabilidad del LogAuditoria: la trazabilidad jurídica NO se edita ni
--     se borra nunca. Se bloquea UPDATE/DELETE a nivel de servidor con trigger:
--     la aplicación no puede violarlo aunque tenga un bug o SQL injection.
--   * Mínimo privilegio: roles separados para la app (DML) y para auditoría
--     (solo lectura), sin TRUNCATE ni TRIGGER para la app.
--   * Determinismo: timezone fijada para el cómputo de plazos procesales.
-- =============================================================================

SET timezone = 'America/Managua';

-- ---------------------------------------------------------------------------
-- 1) Trigger de inmutabilidad sobre log_auditoria
--    (las tablas las crea Alembic/SQLAlchemy; este bloque es idempotente y
--     sobrevive a migraciones futuras porque no toca columnas.)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_bloquear_mutacion_auditoria()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'log_auditoria es INMUTABLE por política de trazabilidad judicial (Ley 908): operacion % prohibida',
        TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON log_auditoria;
CREATE TRIGGER trg_auditoria_inmutable
    BEFORE UPDATE OR DELETE ON log_auditoria
    FOR EACH ROW
    EXECUTE FUNCTION fn_bloquear_mutacion_auditoria();

-- ---------------------------------------------------------------------------
-- 2) Roles de mínimo privilegio. En local se crean con password de desarrollo;
--    en producción/staging se gestionan fuera del repo (vault/secrets manager).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gemelo_app') THEN
        CREATE ROLE gemelo_app LOGIN PASSWORD 'solo-desarrollo-cambiar';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gemelo_audit') THEN
        CREATE ROLE gemelo_audit LOGIN PASSWORD 'solo-desarrollo-cambiar';
    END IF;
END
$$;

-- La app: DML normal sobre el expediente...
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gemelo_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gemelo_app;
-- ...pero SIN poder truncar/borrar triggers de auditoría (defensa doble).
REVOKE TRUNCATE, TRIGGER ON log_auditoria FROM gemelo_app;

-- Auditoría humana (secretaría/inspección judicial): SOLO lectura.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO gemelo_audit;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO gemelo_audit;

-- ---------------------------------------------------------------------------
-- 3) Índice parcial de expedientes VIVOS: el tablero consulta casos abiertos
--    con estado actual; el índice evita escanear el histórico archivado.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_caso_vivo_estado
    ON caso (estado_actual, etapa_actual)
    WHERE cerrado = false;
