import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        research: fileURLToPath(new URL("./research.html", import.meta.url)),
      },
    },
  },
  server: {
    port: 18773,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:18780",
    },
  },
});

