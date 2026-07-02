/**
* ARCADIAN EU cookie preferences
*/
(function() {
  "use strict";

  const cookieConsentKey = "arcadianCookieConsent.v1";
  const cookieBanner = document.querySelector("[data-cookie-banner]");
  const cookieDialog = document.querySelector("[data-cookie-dialog]");
  const preferencesToggle = document.querySelector("#cookie-preferences");
  const analyticsToggle = document.querySelector("#cookie-analytics");
  const marketingToggle = document.querySelector("#cookie-marketing");
  const timeZoneCookieName = "arcadianTimeZone";

  if (!cookieBanner && !cookieDialog) {
    return;
  }

  function readCookiePreferences() {
    try {
      const stored = window.localStorage.getItem(cookieConsentKey);
      return stored ? JSON.parse(stored) : null;
    } catch (error) {
      return null;
    }
  }

  function applyCookiePreferences(preferences) {
    const preferencesAllowed = Boolean(preferences && preferences.preferences);
    const analyticsAllowed = Boolean(preferences && preferences.analytics);
    const marketingAllowed = Boolean(preferences && preferences.marketing);
    document.documentElement.dataset.preferencesConsent = preferencesAllowed ? "granted" : "denied";
    document.documentElement.dataset.analyticsConsent = analyticsAllowed ? "granted" : "denied";
    document.documentElement.dataset.marketingConsent = marketingAllowed ? "granted" : "denied";
    if (preferencesToggle) {
      preferencesToggle.checked = preferencesAllowed;
    }
    if (analyticsToggle) {
      analyticsToggle.checked = analyticsAllowed;
    }
    if (marketingToggle) {
      marketingToggle.checked = marketingAllowed;
    }
    syncTimeZoneCookie(preferencesAllowed);
  }

  function cookieAttributes(maxAge) {
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    return `Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
  }

  function deleteTimeZoneCookie() {
    document.cookie = `${timeZoneCookieName}=; ${cookieAttributes(0)}`;
  }

  function browserTimeZone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (error) {
      return "";
    }
  }

  function syncTimeZoneCookie(allowed) {
    if (!allowed) {
      deleteTimeZoneCookie();
      return;
    }
    const zone = browserTimeZone();
    if (!zone || zone.length > 64 || !/^[A-Za-z0-9_+\-./]+$/.test(zone)) {
      deleteTimeZoneCookie();
      return;
    }
    document.cookie = `${timeZoneCookieName}=${encodeURIComponent(zone)}; ${cookieAttributes(31536000)}`;
  }

  function hideCookieBanner() {
    if (cookieBanner) {
      cookieBanner.hidden = true;
    }
  }

  function closeCookieDialog() {
    if (!cookieDialog) {
      return;
    }
    cookieDialog.hidden = true;
    cookieDialog.setAttribute("aria-hidden", "true");
  }

  function writeCookiePreferences(preferences) {
    const payload = {
      necessary: true,
      preferences: Boolean(preferences.preferences),
      analytics: Boolean(preferences.analytics),
      marketing: Boolean(preferences.marketing),
      updatedAt: new Date().toISOString()
    };

    try {
      window.localStorage.setItem(cookieConsentKey, JSON.stringify(payload));
    } catch (error) {
      // The choice still applies to this page when storage is unavailable.
    }

    applyCookiePreferences(payload);
    hideCookieBanner();
    closeCookieDialog();
  }

  function showCookieBanner() {
    if (cookieBanner) {
      cookieBanner.hidden = false;
    }
  }

  function openCookieDialog() {
    if (!cookieDialog) {
      return;
    }
    cookieDialog.hidden = false;
    cookieDialog.setAttribute("aria-hidden", "false");
    const firstInput = cookieDialog.querySelector("input:not(:disabled), button");
    if (firstInput) {
      firstInput.focus();
    }
  }

  function saveCurrentCookiePreferences() {
    writeCookiePreferences({
      preferences: preferencesToggle && preferencesToggle.checked,
      analytics: analyticsToggle && analyticsToggle.checked,
      marketing: marketingToggle && marketingToggle.checked
    });
  }

  document.querySelectorAll("[data-cookie-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.getAttribute("data-cookie-action");
      if (action === "open") {
        openCookieDialog();
        return;
      }
      if (action === "close") {
        closeCookieDialog();
        return;
      }
      if (action === "accept") {
        writeCookiePreferences({ preferences: true, analytics: true, marketing: true });
        return;
      }
      if (action === "reject") {
        writeCookiePreferences({ preferences: false, analytics: false, marketing: false });
        return;
      }
      if (action === "save") {
        saveCurrentCookiePreferences();
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeCookieDialog();
    }
  });

  const existingCookiePreferences = readCookiePreferences();
  if (existingCookiePreferences) {
    applyCookiePreferences(existingCookiePreferences);
  } else {
    applyCookiePreferences({ preferences: false, analytics: false, marketing: false });
    showCookieBanner();
  }
})();
