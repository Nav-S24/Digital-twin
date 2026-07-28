// src/utils/api.js
// Axios API client for the Vehicle Digital Twin backend.

import axios from 'axios'

const BASE = '/digital_twin'

const api = axios.create({
  baseURL: BASE,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Response interceptor: unwrap data ─────────────────────────────────────
api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail || err.message || 'API error'
    return Promise.reject(new Error(msg))
  }
)

// ── Endpoints ──────────────────────────────────────────────────────────────

export const fetchHealth       = ()           => api.get('/health')
export const fetchFleet        = ()           => api.get('/fleet')
export const fetchVehicleIds   = ()           => api.get('/ids')

export const fetchVehicles = ({
  page = 1, perPage = 50,
  healthClass, urgency,
  sortBy = 'overall_health', ascending = true
} = {}) => {
  const params = { page, per_page: perPage, sort_by: sortBy, ascending }
  if (healthClass) params.health_class = healthClass
  if (urgency)     params.urgency      = urgency
  return api.get('/vehicles', { params })
}

export const fetchCurrentState  = (vid) => api.get(`/current/${vid}`)
export const fetchComponents    = (vid) => api.get(`/components/${vid}`)
export const fetchHistory       = (vid, page = 1, perPage = 200) =>
  api.get(`/history/${vid}`, { params: { page, per_page: perPage } })
export const fetchRisk          = (vid) => api.get(`/risk/${vid}`)
export const fetchRUL           = (vid) => api.get(`/rul/${vid}`)

export const runSimulation = (vehicleId, days) =>
  api.post('/simulate', { vehicle_id: vehicleId, days })

export const refreshData = () => api.get('/refresh')

export default api
