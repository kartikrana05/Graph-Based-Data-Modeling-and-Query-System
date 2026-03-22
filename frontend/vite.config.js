import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Dev only: proxies /api calls to local backend
      "/api": "http://localhost:8000",
    },
  },
  // In production (Vercel), VITE_API_URL points to the Render backend
  define: {
    __API_URL__: JSON.stringify(process.env.VITE_API_URL || ""),
  },
});
