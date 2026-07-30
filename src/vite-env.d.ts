/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OMEGA_API_URL?: string;
  readonly VITE_OMEGA_API_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
