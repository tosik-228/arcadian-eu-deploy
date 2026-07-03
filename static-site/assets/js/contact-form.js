/**
* ARCADIAN contact form for the static App Platform release.
*/
(function () {
  "use strict";

  const MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024;

  document.querySelectorAll(".arcadian-contact-form").forEach((form) => {
    const startedAt = form.querySelector('input[name="startedAt"]');
    const fileInput = form.querySelector('input[type="file"][name="attachment"]');
    const fileLabel = form.querySelector("[data-file-label]");
    const defaultFileLabel = fileLabel ? fileLabel.textContent : "";
    if (startedAt) {
      startedAt.value = String(Date.now());
    }
    if (fileInput) {
      fileInput.addEventListener("change", () => updateFileLabel(fileInput, fileLabel, defaultFileLabel));
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
        const file = fileInput && fileInput.files ? fileInput.files[0] : null;
        if (file && file.size > MAX_ATTACHMENT_BYTES) {
          throw new Error(form.dataset.fileTooLarge || "The file is too large. Please attach a file up to 100 MB.");
        }
        const data = new FormData(form);
        if (!String(data.get("startedAt") || "").trim()) {
          data.delete("startedAt");
        }

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
      }
    });
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
