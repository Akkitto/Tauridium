// Unprivileged, per-document badge signals. Native code validates every value again.
(function () {
  var limit = 1000000;
  function count(value) {
    var n = parseInt(value, 10);
    return Number.isFinite(n) ? Math.min(limit, Math.max(0, n)) : 0;
  }
  window.__pakeUnread = 0;
  window.__pakeSetBadge = function (direct, indirect) {
    var d = count(direct), i = count(indirect);
    window.__pakeBadge = { direct: d, indirect: i };
    // Preserve the legacy total for custom recipes that read/write this value.
    window.__pakeUnread = Math.min(limit, d + i);
  };

  // The standard API is an explicit site-owned unread signal, including zero.
  // Do not infer unread messages from Notification creation/close, focus or time.
  function setAppBadge(contents) {
    try {
      if (typeof contents === 'bigint') throw new TypeError('Badge contents cannot be a BigInt');
      var n = contents === undefined ? 1 : Number(contents);
      // Web IDL [EnforceRange] unsigned long long: reject nonfinite/out-of-range
      // values, truncate fractions, and retain zero as an explicit clear.
      if (!Number.isFinite(n) || Math.trunc(n) < 0 || Math.trunc(n) >= 2 ** 64) {
        throw new TypeError('Badge contents must be an unsigned 64-bit integer');
      }
      window.__pakeAppBadge = Math.min(limit, Math.trunc(n));
      return Promise.resolve();
    } catch (error) {
      return Promise.reject(error);
    }
  }
  function clearAppBadge() {
    window.__pakeAppBadge = 0;
    return Promise.resolve();
  }
  // Read-only engine descriptors should not prevent recipe fallback or page load.
  try {
    Object.defineProperties(window.navigator, {
      setAppBadge: { value: setAppBadge, configurable: true, writable: true },
      clearAppBadge: { value: clearAppBadge, configurable: true, writable: true }
    });
  } catch (_) {
    console.warn('[Tauridium] Browser badge API unavailable; using recipe counts');
  }
})();
