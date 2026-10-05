interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_TERM_ID?: string
  readonly VITE_MAPBOX_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
