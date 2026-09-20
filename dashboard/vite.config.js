import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard fetches the report API at /services/report/... -- a
// relative path, so the built bundle works behind the gateway on any
// host (see src/api.js).
//
// The dev server is not behind that gateway, so it proxies the same
// prefix itself. The prefix therefore has to match deploy/nginx.conf;
// if you change it in one place, change it in both (backlog BL-071).
//
// Override the target when the report service is not on the default
// published port:  MEMSOC_REPORT_PROXY=http://localhost:9001 npm run dev
const REPORT_TARGET =
  process.env.MEMSOC_REPORT_PROXY || 'http://localhost:8001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Strips the prefix, exactly as the nginx location does, so the
      // report service sees /api/reports either way.
      '/services/report': {
        target: REPORT_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/services\/report/, ''),
      },
    },
  },
})
