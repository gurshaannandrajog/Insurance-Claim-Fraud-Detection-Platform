import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to Django so the browser sees ONE origin:
// session + CSRF cookies work without cross-site cookie settings.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000", changeOrigin: false } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000", changeOrigin: false } },
  },
});
