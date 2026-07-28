import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev proxy: mirrors gateway/nginx.conf's routing so the same
// relative /api/phaseN/ calls work identically in `npm run dev` (talking
// to backends on localhost) and in the Docker Compose stack (talking to
// backends by container name via the nginx gateway).
const PORTS = {
  phase2: 8002, phase3: 8003, phase4: 8004, phase5: 8005,
  phase6: 8006, phase7: 8007, phase8: 8008, phase9: 8009,
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      Object.entries(PORTS).map(([name, port]) => [
        `/api/${name}`,
        {
          target: `http://localhost:${port}`,
          changeOrigin: true,
          rewrite: (path) =>
            // Phase 4's own routes are prefixed with /digital_twin
            name === "phase4"
              ? path.replace(/^\/api\/phase4/, "/digital_twin")
              : path.replace(new RegExp(`^/api/${name}`), ""),
        },
      ])
    ),
  },
});
