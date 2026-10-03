interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_TERM_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
