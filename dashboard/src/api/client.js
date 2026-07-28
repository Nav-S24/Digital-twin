import axios from "axios";

// In production (Docker), the gateway serves this app AND proxies
// /api/phaseN/ to each backend from the same origin, so relative paths
// work with zero CORS configuration. In local dev (`npm run dev`), Vite's
// dev server proxy (see vite.config.js) forwards the same paths to each
// backend running on localhost.
const make = (base) => axios.create({ baseURL: base, timeout: 30000 });

export const phase2 = make("/api/phase2"); // Health Score
export const phase3 = make("/api/phase3"); // Predictive Maintenance
export const phase4 = make("/api/phase4"); // Digital Twin
export const phase5 = make("/api/phase5"); // OBD Diagnostics
export const phase6 = make("/api/phase6"); // Knowledge Base / RAG
export const phase7 = make("/api/phase7"); // NL Assistant
export const phase8 = make("/api/phase8"); // Trip Intelligence
export const phase9 = make("/api/phase9"); // Driver Behaviour

export const ALL_SERVICES = [
  { id: "phase2", name: "Health Score", client: phase2, healthPath: "/health" },
  { id: "phase3", name: "Predictive Maintenance", client: phase3, healthPath: "/health" },
  { id: "phase4", name: "Digital Twin", client: phase4, healthPath: "/health" },
  { id: "phase5", name: "OBD Diagnostics", client: phase5, healthPath: "/health" },
  { id: "phase6", name: "Knowledge Base", client: phase6, healthPath: "/health" },
  { id: "phase7", name: "Assistant", client: phase7, healthPath: "/health" },
  { id: "phase8", name: "Trip Intelligence", client: phase8, healthPath: "/health" },
  { id: "phase9", name: "Driver Behaviour", client: phase9, healthPath: "/health" },
];
