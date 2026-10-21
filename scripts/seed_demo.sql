-- =============================================================================
-- seed_demo.sql — Expediente DEMO navegable en el tablero (desarrollo local).
-- Ejecutar DESPUÉS de que el backend haya creado el esquema (create_all al
-- arrancar):  docker compose exec -T db psql -U gemelo_dev -d gemelo_civil \
--               -f - < scripts/seed_demo.sql
-- Idempotente: si el expediente ya existe, no duplica nada.
-- Al terminar imprime el UUID a pegar en http://localhost:3005
-- =============================================================================
BEGIN;

INSERT INTO actor_juridico (id, tipo_persona, nombre_razon_social, cedula_ruc,
                            rol_principal, activo, created_at, updated_at)
VALUES
 ('00000000-0000-0000-0000-00000000d001','natural', 'Dra. Jueza Demo',        'J-DEMO-001','juez',true, now(),now()),
 ('00000000-0000-0000-0000-00000000d002','juridica','Inmobiliaria Demo S.A.', 'RUC-DTE-001','demandante',true, now(),now()),
 ('00000000-0000-0000-0000-00000000d003','natural', 'Arrendatario Demo',      '001-250380-1000A','demandado',true, now(),now())
ON CONFLICT DO NOTHING;

INSERT INTO caso (id, numero_expediente, tipo_proceso, materia, juzgado_asignado,
                  etapa_actual, estado_actual, fecha_presentacion_demanda, cerrado,
                  juez_id, created_at, updated_at)
VALUES
 ('00000000-0000-0000-0000-00000000c001','00001-2026-CIV-ORD','juicio_ordinario_civil',
  'arrendaticio','Juzgado Civil de Managua','calificacion_demanda','presentado',
  CURRENT_DATE,false,'00000000-0000-0000-0000-00000000d001',now(),now())
ON CONFLICT (numero_expediente) DO NOTHING;

INSERT INTO pretension (id, caso_id, codigo_tipo, orden, descripcion,
                        es_principal, resuelta, created_at, updated_at)
VALUES
 ('00000000-0000-0000-0000-00000000p001','00000000-0000-0000-0000-00000000c001',
  'desalojo',1,'Se declare rescindido el contrato de arrendamiento y se ordene la entrega material del inmueble.','true','false',now(),now())
ON CONFLICT DO NOTHING;

INSERT INTO caso_actor (caso_id, actor_id, rol_en_caso, desde)
VALUES
 ('00000000-0000-0000-0000-00000000c001','00000000-0000-0000-0000-00000000d002','demandante',now()),
 ('00000000-0000-0000-0000-00000000c001','00000000-0000-0000-0000-00000000d003','demandado',now())
ON CONFLICT DO NOTHING;

COMMIT;

SELECT id AS uuid_para_el_tablero FROM caso WHERE numero_expediente='00001-2026-CIV-ORD';
