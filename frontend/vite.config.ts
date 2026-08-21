import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Tauri expects a fixed port in dev (src-tauri/tauri.conf.json -> devUrl).
  server: { port: 1420, strictPort: true },
  build: { target: "es2022" },
});
