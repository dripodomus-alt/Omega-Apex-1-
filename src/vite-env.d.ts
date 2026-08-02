/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_POLYGON_PROD_RPC_URL?: string;
  readonly VITE_POLYGON_RPC_URL?: string;
  readonly VITE_EXECUTOR_WALLET?: string;
  readonly VITE_OTHER_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
