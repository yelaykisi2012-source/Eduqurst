import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, // listen on 0.0.0.0 so a tunnel (ngrok/cloudflared) can reach it
    port: 5173,
    // Local dev calls same-origin /api (see api.ts); proxy it to the live
    // backend so the browser never hits CORS for localhost:5173.
    // Set VITE_PROXY_TARGET (e.g. http://127.0.0.1:8010) to point the dev server
    // at a backend running on this machine instead.
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "https://eduqurst.onrender.com",
        changeOrigin: true,
        secure: true,
      },
    },
  },
});
