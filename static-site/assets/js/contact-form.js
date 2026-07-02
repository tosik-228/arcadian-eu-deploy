/**
* ARCADIAN contact form for the static App Platform release.
*/
(function () {
  "use strict";

  document.querySelectorAll(".arcadian-contact-form").forEach((form) => {
    const startedAt = form.querySelector('input[name="startedAt"]');
    if (startedAt) {
      startedAt.value = String(Date.now());
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const action = form.getAttribute("action");
      const loading = form.querySelector(".loading");
      const errorMessage = form.querySelector(".error-message");
      const sentMessage = form.querySelector(".sent-message");

      if (!action) {
        showError(loading, errorMessage, "The contact form is not configured.");
        return;
      }

      loading.classList.add("d-block");
      errorMessage.classList.remove("d-block");
      sentMessage.classList.remove("d-block");

      try {
        const data = Object.fromEntries(new FormData(form).entries());
        data.startedAt = Number(data.startedAt || Date.now());

        const response = await fetch(action, {
          method: "POST",
          body: JSON.stringify(data),
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
          }
        });
        const text = await response.text();

        if (!response.ok) {
          const serverMessage = text.trim();
          throw new Error(serverMessage && serverMessage.length <= 180
            ? serverMessage
            : "The message could not be sent. Please check the form and try again.");
        }

        const payload = parseJson(text);
        const successMessage = payload && payload.message ? payload.message : text.trim();
        if (successMessage && successMessage !== "OK") {
          sentMessage.textContent = successMessage;
        }

        loading.classList.remove("d-block");
        sentMessage.classList.add("d-block");
        form.reset();
        if (startedAt) {
          startedAt.value = String(Date.now());
        }
      } catch (error) {
        showError(loading, errorMessage, error.message || "The message could not be sent.");
      }
    });
  });

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
