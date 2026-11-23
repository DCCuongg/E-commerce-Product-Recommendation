/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_ORDER_API_URL?: string;
  readonly VITE_RECOMMENDER_API_URL?: string;
  readonly VITE_AUTH_API_URL?: string;
  readonly VITE_FAAS_URL?: string;
  readonly VITE_DEMO_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}