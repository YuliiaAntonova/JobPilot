/**
 * fetch wrapper with timeout (avoids hanging when the API is unreachable).
 */

export async function fetchWithTimeout(url, opts = {}) {
  const { timeoutMs = 90_000, ...rest } = opts;
  const c = new AbortController();
  const t = window.setTimeout(() => c.abort(new DOMException("timeout", "AbortError")), timeoutMs);
  try {
    return await fetch(url, { ...rest, signal: c.signal });
  } finally {
    window.clearTimeout(t);
  }
}
