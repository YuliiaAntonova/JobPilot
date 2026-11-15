import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: path.resolve(__dirname, "../job_application/static/app"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          motion: ["framer-motion"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/profile": "http://127.0.0.1:8000",
      "/analyze": "http://127.0.0.1:8000",
      "/jobs": "http://127.0.0.1:8000",
      "/docs": "http://127.0.0.1:8000",
      "/openapi.json": "http://127.0.0.1:8000",
      "/redoc": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/about": "http://127.0.0.1:8000",
    },
  },
});
