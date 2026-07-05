/**
 * ARCADIAN EU → Werfvolt ops beacon.
 *
 * Sends one anonymous page-view ping per page load to the Werfvolt ops console
 * (the App Platform site has no access log we control). The ping carries only
 * path, referrer and query string — the same data a normal server access log
 * would hold. A persistent visitor id is attached ONLY when the user granted
 * "analytics" in the cookie preferences (arcadianCookieConsent.v1).
 */
(function () {
  "use strict";
  try {
    var consent = null;
    try { consent = JSON.parse(window.localStorage.getItem("arcadianCookieConsent.v1")); } catch (e) { /* no consent stored */ }
    var visitor = "";
    if (consent && consent.analytics) {
      var key = "arcadianVisitor.v1";
      visitor = window.localStorage.getItem(key) || "";
      if (!visitor) {
        visitor = (window.crypto && window.crypto.randomUUID)
          ? window.crypto.randomUUID()
          : String(Date.now()) + "-" + Math.random().toString(36).slice(2, 10);
        window.localStorage.setItem(key, visitor);
      }
    }
    var payload = JSON.stringify({
      p: window.location.pathname,
      r: document.referrer || "",
      u: window.location.search.slice(0, 180),
      v: visitor
    });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("https://werfvolt.be/api/public/landing-hit",
        new Blob([payload], { type: "text/plain" }));
    }
  } catch (e) { /* the beacon must never break the page */ }
})();
