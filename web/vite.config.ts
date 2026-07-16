import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_PROXY_API_TARGET || "http://localhost:8080";
const TILES_TARGET = process.env.VITE_PROXY_TILES_TARGET || "http://localhost:3000";

// The browser talks ONLY to the web origin. These proxies keep us same-origin
// so there is never a CORS negotiation with corridor-api or Martin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
      "/tiles": {
        target: TILES_TARGET,
        changeOrigin: true,
        // Martin serves at its root, so strip the /tiles prefix off the path.
        rewrite: (path) => path.replace(/^\/tiles/, ""),
      },
    },
  },
});
