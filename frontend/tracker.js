/**
 * Behavioral Tracker: browser-side capture layer
 *
 * Silently records mouse movement, scrolling, clicks, and keystrokes,
 * then sends the session payload to the backend pipeline.
 *
 * Drop onto any page:
 *   <script src="tracker.js"></script>
 *
 * Privacy: actual key characters are never recorded, only "key" placeholders.
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // Configuration
  // ---------------------------------------------------------------------------
  var BACKEND_URL = (window.location.origin || "http://localhost:5000") + "/session";
  var SEND_INTERVAL_MS = 60000; // auto-send every 60 s for long sessions
  var MOUSEMOVE_THROTTLE_MS = 50;

  // ---------------------------------------------------------------------------
  // User ID: persist in localStorage so each browser has a stable identity
  // ---------------------------------------------------------------------------
  function getOrCreateUserId() {
    var key = "behavioral_tracker_uid";
    var uid = "sandro_test";
    try { localStorage.setItem(key, uid); } catch (_) {}
    return uid;
  }

  var userId = getOrCreateUserId();

  // ---------------------------------------------------------------------------
  // Session state
  // ---------------------------------------------------------------------------
  var sessionStart = performance.now();
  var mouseMovement = [];
  var scrollEvents = [];
  var clicks = [];
  var keystrokes = [];

  // Map of keys currently held down  ->  { down: elapsed }
  var pendingKeys = {};

  function elapsed() {
    return Math.round(performance.now() - sessionStart);
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  // Mouse movement (throttled)
  var lastMouseTime = 0;
  document.addEventListener(
    "mousemove",
    function (e) {
      var now = performance.now();
      if (now - lastMouseTime < MOUSEMOVE_THROTTLE_MS) return;
      lastMouseTime = now;
      mouseMovement.push({ x: e.clientX, y: e.clientY, t: elapsed() });
    },
    { passive: true }
  );

  // -- Scroll --
  window.addEventListener(
    "scroll",
    function () {
      scrollEvents.push({
        delta: Math.round(window.scrollY),
        t: elapsed(),
      });
    },
    { passive: true }
  );

  // More precise scroll delta via wheel event
  document.addEventListener(
    "wheel",
    function (e) {
      scrollEvents.push({
        delta: Math.round(Math.abs(e.deltaY)),
        t: elapsed(),
      });
    },
    { passive: true }
  );

  // -- Clicks --
  document.addEventListener(
    "click",
    function (e) {
      clicks.push({ x: e.clientX, y: e.clientY, t: elapsed() });
    },
    { passive: true }
  );

  // -- Keystrokes (privacy-safe: no actual characters) --
  document.addEventListener(
    "keydown",
    function (e) {
      // Use a hash of the key code as an anonymous identifier per physical key
      var id = e.code || "unknown";
      if (!pendingKeys[id]) {
        pendingKeys[id] = { down: elapsed() };
      }
    },
    { passive: true }
  );

  document.addEventListener(
    "keyup",
    function (e) {
      var id = e.code || "unknown";
      var pending = pendingKeys[id];
      if (pending) {
        keystrokes.push({ key: "key", down: pending.down, up: elapsed() });
        delete pendingKeys[id];
      }
    },
    { passive: true }
  );

  // ---------------------------------------------------------------------------
  // Payload builder + sender
  // ---------------------------------------------------------------------------
  function buildPayload() {
    return {
      user_id: userId,
      mouse_movement: mouseMovement.slice(),
      scroll_events: scrollEvents.slice(),
      clicks: clicks.slice(),
      keystrokes: keystrokes.slice(),
    };
  }

  function resetBuffers() {
    mouseMovement = [];
    scrollEvents = [];
    clicks = [];
    keystrokes = [];
    pendingKeys = {};
    sessionStart = performance.now();
  }

  function sendPayload() {
    var payload = buildPayload();

    // Only send if there is meaningful data
    var total =
      payload.mouse_movement.length +
      payload.scroll_events.length +
      payload.clicks.length +
      payload.keystrokes.length;
    if (total === 0) return;

    var blob = new Blob([JSON.stringify(payload)], {
      type: "application/json",
    });

    // sendBeacon is fire-and-forget: survives page close
    if (navigator.sendBeacon) {
      navigator.sendBeacon(BACKEND_URL, blob);
    } else {
      // Fallback for older browsers
      var xhr = new XMLHttpRequest();
      xhr.open("POST", BACKEND_URL, true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.send(JSON.stringify(payload));
    }

    resetBuffers();
  }

  // ---------------------------------------------------------------------------
  // Automatic sending
  // ---------------------------------------------------------------------------

  // Periodic send for long sessions
  setInterval(sendPayload, SEND_INTERVAL_MS);

  // Send on page close
  window.addEventListener("beforeunload", sendPayload);

  // ---------------------------------------------------------------------------
  // Public API (optional: for dashboard or debugging)
  // ---------------------------------------------------------------------------
  window.__behaviorTracker = {
    getUserId: function () {
      return userId;
    },
    getPayload: buildPayload,
    sendNow: sendPayload,
  };
})();
