/* Small transport module shared by the UI and offline regression tests. */
(function (root) {
  'use strict';
  async function request(base, token, path, body, method) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const result = await fetch(base.replace(/\/$/, '') + path, {
        method: method || (body ? 'POST' : 'GET'),
        headers: { 'X-BuiltWatch-Request': '1', ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
        signal: controller.signal,
      });
      let data;
      try { data = await result.json(); } catch { data = {}; }
      if (!result.ok) {
        const fallback = result.status === 401
          ? 'Please sign in again to open your workspace.'
          : result.status === 429
            ? 'Your workspace is busy with a check. Wait a few minutes and refresh. Your connection has been kept.'
            : 'The workspace service is unavailable. Try again shortly. Your connection has been kept.';
        const error = new Error(data.error || fallback);
        error.status = result.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') {
        throw new Error('The workspace took too long to respond. Try refreshing in a minute; your connection has been kept.');
      }
      if (error instanceof TypeError) {
        throw new Error('Could not connect. Check your internet connection, then try again. Your saved data is still stored in your account.');
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  root.BuiltWatchClient = { request };
})(typeof window !== 'undefined' ? window : globalThis);
