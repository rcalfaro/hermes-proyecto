/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL base del backend FastAPI; vacío = mismo origen (proxy en dev). */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
