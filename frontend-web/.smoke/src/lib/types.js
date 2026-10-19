/**
 * Tipos compartidos del Gemelo Digital — espejo exacto de los DTOs Pydantic
 * del backend FastAPI (app/api/queries.py y app/api/endpoints.py).
 *
 * Convención: los estados/etapas llegan como strings crudos del enum Python
 * (EstadoProcesal / EtapaProcesal), por eso se modelan como uniones literales
 * para que el compilador obligue a cubrir cada valor en el semáforo visual.
 */
/** Error HTTP normalizado del backend (FastAPI { detail } o validación 422). */
export class ApiError extends Error {
    status;
    detail;
    constructor(status, message, detail) {
        super(message);
        this.status = status;
        this.detail = detail;
        this.name = 'ApiError';
    }
}
