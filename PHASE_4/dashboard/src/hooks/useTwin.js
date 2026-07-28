// src/hooks/useTwin.js
import { useState, useEffect, useCallback } from 'react'
import {
  fetchCurrentState, fetchComponents, fetchHistory,
  fetchRisk, fetchRUL, fetchFleet, fetchVehicles, runSimulation
} from '../utils/api'

// Generic fetcher hook
function useFetch(fetchFn, deps = []) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchFn()
      setData(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load() }, [load])
  return { data, loading, error, reload: load }
}

// ── Per-vehicle hooks ────────────────────────────────────────────────────

export function useVehicleState(vehicleId) {
  return useFetch(() => fetchCurrentState(vehicleId), [vehicleId])
}

export function useComponents(vehicleId) {
  return useFetch(() => fetchComponents(vehicleId), [vehicleId])
}

export function useHistory(vehicleId) {
  return useFetch(() => fetchHistory(vehicleId), [vehicleId])
}

export function useRisk(vehicleId) {
  return useFetch(() => fetchRisk(vehicleId), [vehicleId])
}

export function useRUL(vehicleId) {
  return useFetch(() => fetchRUL(vehicleId), [vehicleId])
}

// ── Fleet hooks ──────────────────────────────────────────────────────────

export function useFleet() {
  return useFetch(fetchFleet, [])
}

export function useVehicleList(filters = {}) {
  const { page = 1, perPage = 50, healthClass, urgency, sortBy, ascending } = filters
  return useFetch(
    () => fetchVehicles({ page, perPage, healthClass, urgency, sortBy, ascending }),
    [page, perPage, healthClass, urgency, sortBy, ascending]
  )
}

// ── Simulation hook ──────────────────────────────────────────────────────

export function useSimulation(vehicleId, days) {
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const run = useCallback(async (vId, d) => {
    setLoading(true)
    setError(null)
    try {
      const res = await runSimulation(vId, d)
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (vehicleId && days) run(vehicleId, days)
  }, [vehicleId, days, run])

  return { result, loading, error, run }
}
