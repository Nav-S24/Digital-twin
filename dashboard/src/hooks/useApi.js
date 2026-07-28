import { useEffect, useState, useCallback } from "react";

/**
 * Fetches `fn()` (an async function returning data) whenever `deps` change.
 * Returns { data, loading, error, refetch }.
 */
export function useApi(fn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fn()
      .then((res) => { if (!cancelled) setData(res); })
      .catch((err) => { if (!cancelled) setError(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, loading, error, refetch };
}

export function errorMessage(err, serviceName) {
  if (!err) return null;
  if (err.code === "ERR_NETWORK" || !err.response) {
    return `Can't reach the ${serviceName} service. Is it running?`;
  }
  if (err.response?.status === 404) return `${serviceName}: not found.`;
  return err.response?.data?.detail || `${serviceName} returned an error.`;
}
