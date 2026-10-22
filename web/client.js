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
      try { data = await result.json(); } catch { data = null; }
      if (!result.ok) {
        const fallback = result.status === 401
          ? 'Please sign in again to open your workspace.'
          : result.status === 429
            ? 'Your workspace is busy with a check. Wait a few minutes and refresh. Your connection has been kept.'
            : 'The workspace service is unavailable. Try again shortly. Your connection has been kept.';
        const error = new Error(typeof data?.error === 'string' && data.error || fallback);
        error.status = result.status;
        error.code = data?.code;
        throw error;
      }
      // A proxy's HTML/partial body is an unknown outcome, not a successful
      // save or a signed-out session. Never retry a mutation automatically.
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        throw new Error('The workspace returned an unreadable response. Refresh to check the current state before trying the action again.');
      }
      // These reads control session identity and replace the entire visible desk.
      // Missing fields are a transport failure, never evidence of sign-out/emptiness.
      const read = (method || (body ? 'POST' : 'GET')) === 'GET';
      if (read && ((path === '/api/session' && typeof data.signed_in !== 'boolean')
        || (path === '/api/workspace' && (data.demo !== false
          || !['systems', 'findings', 'sources', 'runs'].every(key => Array.isArray(data[key])))))) {
        throw new Error('The workspace returned an incomplete response. Your last view has been kept. Refresh to try again.');
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
