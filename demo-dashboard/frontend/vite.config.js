import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/static": "http://localhost:8090",
      "/live": "http://localhost:8090",
    },
  },
});
