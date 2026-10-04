/**
* ARCADIAN contact form for the static App Platform release.
*/
(function () {
  "use strict";

  const MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024;
  const TURNSTILE_ACTION = "arcadian_contact";
  const TURNSTILE_RESPONSE_FIELD = "cf-turnstile-response";
  const TURNSTILE_SITEKEY_PLACEHOLDER = "__TURNSTILE_" + "SITEKEY__";
  const TURNSTILE_LOAD_TIMEOUT_MS = 10000;

  document.querySelectorAll(".arcadian-contact-form").forEach((form) => {
    const startedAt = form.querySelector('input[name="startedAt"]');
    const fileInput = form.querySelector('input[type="file"][name="attachment"]');
    const fileLabel = form.querySelector("[data-file-label]");
    const defaultFileLabel = fileLabel ? fileLabel.textContent : "";
    const submitButton = form.querySelector('button[type="submit"]');
    const turnstileContainer = form.querySelector("[data-turnstile-container]");
    const turnstileStatus = form.querySelector("[data-turnstile-status]");
    let widgetId = null;
    let turnstileToken = "";
    let turnstileReady = false;
    let requestInFlight = false;

    setSubmitEnabled(false);
    if (startedAt) {
      startedAt.value = String(Date.now());
    }
    if (fileInput) {
      fileInput.addEventListener("change", () => updateFileLabel(fileInput, fileLabel, defaultFileLabel));
    }
    initializeTurnstile();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const action = form.getAttribute("action");
      const loading = form.querySelector(".loading");
      const errorMessage = form.querySelector(".error-message");
      const sentMessage = form.querySelector(".sent-message");
      let requestAttempted = false;

      if (requestInFlight) {
        return;
      }
      if (!action) {
        showError(loading, errorMessage, "The contact form is not configured.");
        return;
      }
      if (!turnstileReady || !turnstileToken) {
        setTurnstileStatus(form.dataset.turnstileRequired);
        setSubmitEnabled(false);
        return;
      }

      requestInFlight = true;
      setSubmitEnabled(false);
      loading.classList.add("d-block");
      errorMessage.classList.remove("d-block");
      sentMessage.classList.remove("d-block");

      try {
        const file = fileInput && fileInput.files ? fileInput.files[0] : null;
        if (file && file.size > MAX_ATTACHMENT_BYTES) {
          throw new Error(form.dataset.fileTooLarge || "The file is too large. Please attach a file up to 50 MB.");
        }
        const data = new FormData(form);
        const responseToken = String(data.get(TURNSTILE_RESPONSE_FIELD) || "").trim();
        if (!responseToken || responseToken !== turnstileToken) {
          invalidateTurnstile(form.dataset.turnstileRequired, true);
          throw new Error(form.dataset.turnstileRequired || "Complete the anti-bot check before sending.");
        }
        if (!String(data.get("startedAt") || "").trim()) {
          data.delete("startedAt");
        }

        requestAttempted = true;
        const response = await fetch(action, {
          method: "POST",
          body: data
        });
        const text = await response.text();

        if (!response.ok) {
          const payload = parseJson(text);
          const serverMessage = payload && (payload.message || payload.error)
            ? (payload.message || payload.error) : text.trim();
          throw new Error(serverMessage && serverMessage.length <= 180
            ? serverMessage
            : "The message could not be sent. Please check the form and try again.");
        }

        const payload = parseJson(text);
        if (payload && payload.message) {
          sentMessage.textContent = payload.message;
        }

        loading.classList.remove("d-block");
        sentMessage.classList.add("d-block");
        form.reset();
        updateFileLabel(fileInput, fileLabel, defaultFileLabel);
        if (startedAt) {
          startedAt.value = String(Date.now());
        }
      } catch (error) {
        showError(loading, errorMessage, error.message || "The message could not be sent.");
      } finally {
        requestInFlight = false;
        if (requestAttempted) {
          resetTurnstile();
        } else {
          setSubmitEnabled(turnstileReady);
        }
      }
    });

    function initializeTurnstile() {
      const sitekey = turnstileContainer ? String(turnstileContainer.dataset.sitekey || "").trim() : "";
      if (!turnstileContainer || !sitekey || sitekey === TURNSTILE_SITEKEY_PLACEHOLDER) {
        setTurnstileStatus(form.dataset.turnstileConfig);
        return;
      }

      const deadline = Date.now() + TURNSTILE_LOAD_TIMEOUT_MS;
      waitForTurnstile(deadline, sitekey);
    }

    function waitForTurnstile(deadline, sitekey) {
      if (window.turnstile && typeof window.turnstile.ready === "function") {
        window.turnstile.ready(() => renderTurnstile(sitekey));
        return;
      }
      if (Date.now() >= deadline) {
        setTurnstileStatus(form.dataset.turnstileUnavailable);
        return;
      }
      window.setTimeout(() => waitForTurnstile(deadline, sitekey), 200);
    }

    function renderTurnstile(sitekey) {
      try {
        widgetId = window.turnstile.render(turnstileContainer, {
          sitekey: sitekey,
          action: TURNSTILE_ACTION,
          appearance: "always",
          size: turnstileContainer.clientWidth < 300 ? "compact" : "flexible",
          retry: "auto",
          "response-field": true,
          "response-field-name": TURNSTILE_RESPONSE_FIELD,
          callback: (token) => {
            turnstileToken = String(token || "").trim();
            turnstileReady = Boolean(turnstileToken);
            setTurnstileStatus("");
            setSubmitEnabled(turnstileReady);
          },
          "expired-callback": () => {
            invalidateTurnstile(form.dataset.turnstileExpired, true);
          },
          "timeout-callback": () => {
            invalidateTurnstile(form.dataset.turnstileExpired, true);
          },
          "error-callback": () => {
            invalidateTurnstile(form.dataset.turnstileError, false);
          }
        });
      } catch (error) {
        setTurnstileStatus(form.dataset.turnstileUnavailable);
        setSubmitEnabled(false);
      }
    }

    function invalidateTurnstile(message, shouldReset) {
      turnstileToken = "";
      turnstileReady = false;
      setSubmitEnabled(false);
      setTurnstileStatus(message);
      if (shouldReset) {
        resetTurnstile();
      }
    }

    function resetTurnstile() {
      turnstileToken = "";
      turnstileReady = false;
      setSubmitEnabled(false);
      if (widgetId !== null && window.turnstile && typeof window.turnstile.reset === "function") {
        window.turnstile.reset(widgetId);
      }
    }

    function setSubmitEnabled(enabled) {
      if (!submitButton) {
        return;
      }
      const canSubmit = Boolean(enabled) && !requestInFlight;
      submitButton.disabled = !canSubmit;
      submitButton.setAttribute("aria-disabled", String(!canSubmit));
    }

    function setTurnstileStatus(message) {
      if (!turnstileStatus) {
        return;
      }
      turnstileStatus.textContent = message || "";
      turnstileStatus.classList.toggle("is-visible", Boolean(message));
    }
  });

  function updateFileLabel(fileInput, fileLabel, defaultFileLabel) {
    if (!fileInput || !fileLabel) {
      return;
    }
    const file = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
    const wrapper = fileInput.closest(".file-upload");
    if (wrapper) {
      wrapper.classList.toggle("is-selected", Boolean(file));
    }
    fileLabel.textContent = file ? `${file.name} (${formatSize(file.size)})` : defaultFileLabel;
  }

  function formatSize(size) {
    if (size < 1024) {
      return `${size} B`;
    }
    if (size < 1024 * 1024) {
      return `${Math.round(size / 1024)} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function showError(loading, errorMessage, message) {
    loading.classList.remove("d-block");
    errorMessage.textContent = message;
    errorMessage.classList.add("d-block");
  }

  function parseJson(text) {
    if (!text || !text.trim().startsWith("{")) {
      return null;
    }
    try {
      return JSON.parse(text);
    } catch (error) {
      return null;
    }
  }
})();
