(function () {
    "use strict";

    const MIN_WIDTH = 800;
    const DEBOUNCE_MS = 2000;
    const body = document.body;

    if (!body.classList.contains("change-form")) {
        return;
    }
    if (body.classList.contains("popup")) {
        return;
    }

    const previewModels = ["entry", "blogmark", "quotation", "note"];
    const modelClass = previewModels.find((model) =>
        body.classList.contains(`model-${model}`)
    );
    if (!body.classList.contains("app-blog") || !modelClass) {
        return;
    }

    const form = document.querySelector("#content-main form[method='post']");
    const draftCheckbox = form && form.querySelector("input[type='checkbox'][name='is_draft']");
    const viewOnSiteLink = Array.from(
        document.querySelectorAll(".object-tools a[href]")
    ).find((link) => link.textContent.trim().toLowerCase() === "view on site");

    if (!form || !draftCheckbox || !viewOnSiteLink) {
        return;
    }

    const mediaQuery = window.matchMedia(`(min-width: ${MIN_WIDTH}px)`);
    let pane = null;
    let frame = null;
    let status = null;
    let saveTimer = null;
    let statusTimer = null;
    let saveInProgress = false;
    let dirtyAfterSave = false;

    function previewUrl() {
        const url = new URL(viewOnSiteLink.getAttribute("href"), window.location.href);
        url.searchParams.set("_live_preview", Date.now().toString());
        return url.href;
    }

    function ensurePane() {
        if (pane) {
            return;
        }
        pane = document.createElement("aside");
        pane.className = "admin-live-preview-pane";
        pane.setAttribute("aria-label", "Preview");

        frame = document.createElement("iframe");
        frame.className = "admin-live-preview-frame";
        frame.title = "Preview";
        frame.src = previewUrl();

        status = document.createElement("div");
        status.className = "admin-live-preview-status";
        status.setAttribute("aria-live", "polite");

        pane.appendChild(frame);
        document.body.appendChild(pane);
        document.body.appendChild(status);
    }

    function showStatus(message, state, timeout) {
        if (!status) {
            return;
        }
        window.clearTimeout(statusTimer);
        status.textContent = message;
        status.dataset.state = state || "";
        status.dataset.visible = message ? "true" : "false";
        if (message && timeout) {
            statusTimer = window.setTimeout(() => {
                status.dataset.visible = "false";
            }, timeout);
        }
    }

    function active() {
        return draftCheckbox.checked && mediaQuery.matches;
    }

    function updatePreviewMode() {
        if (active()) {
            ensurePane();
            body.classList.add("admin-live-preview-active");
            if (!frame.getAttribute("src")) {
                frame.src = previewUrl();
            }
        } else {
            body.classList.remove("admin-live-preview-active");
            window.clearTimeout(saveTimer);
            showStatus("", "");
        }
    }

    function refreshPreview() {
        if (frame && active()) {
            frame.src = previewUrl();
        }
    }

    function collectValidationMessage(html) {
        const doc = new DOMParser().parseFromString(html, "text/html");
        const nodes = doc.querySelectorAll(".errornote, .errorlist li");
        const messages = Array.from(nodes)
            .map((node) => node.textContent.trim().replace(/\s+/g, " "))
            .filter(Boolean);
        return {
            hasErrors: messages.length > 0,
            message: Array.from(new Set(messages)).slice(0, 3).join(" "),
        };
    }

    function prepareFormData() {
        const submitEvent = new Event("submit", {
            bubbles: true,
            cancelable: true,
        });
        if (!form.dispatchEvent(submitEvent)) {
            return null;
        }
        const data = new FormData(form);
        data.delete("_save");
        data.delete("_saveasnew");
        data.delete("_addanother");
        data.set("_continue", "1");
        data.set("_autosave", "1");
        return data;
    }

    async function autosave() {
        if (!active()) {
            return;
        }
        if (saveInProgress) {
            dirtyAfterSave = true;
            return;
        }

        const data = prepareFormData();
        if (!data) {
            showStatus("Autosave blocked", "error", 4000);
            return;
        }

        saveInProgress = true;
        showStatus("Autosaving...", "saving");

        try {
            const action = form.getAttribute("action") || window.location.href;
            const expectedUrl = new URL(action, window.location.href);
            const response = await fetch(expectedUrl.href, {
                body: data,
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                method: "POST",
            });
            const html = await response.text();
            const finalUrl = new URL(response.url || expectedUrl.href, window.location.href);
            const validation = collectValidationMessage(html);
            const looksSaved =
                response.ok &&
                !validation.hasErrors &&
                finalUrl.pathname === expectedUrl.pathname &&
                (response.redirected || html.includes("was changed successfully"));

            if (looksSaved) {
                showStatus("Saved", "saved", 1800);
                refreshPreview();
            } else {
                showStatus(validation.message || "Autosave failed", "error", 8000);
            }
        } catch (error) {
            showStatus("Autosave failed", "error", 8000);
        } finally {
            saveInProgress = false;
            if (dirtyAfterSave) {
                dirtyAfterSave = false;
                scheduleAutosave();
            }
        }
    }

    function scheduleAutosave() {
        if (!active()) {
            updatePreviewMode();
            return;
        }
        window.clearTimeout(saveTimer);
        showStatus("Unsaved changes", "pending", 1200);
        saveTimer = window.setTimeout(autosave, DEBOUNCE_MS);
    }

    function fieldChanged(event) {
        if (event.target === draftCheckbox) {
            updatePreviewMode();
            if (draftCheckbox.checked) {
                scheduleAutosave();
            }
            return;
        }
        if (!event.target.closest || !event.target.closest("form")) {
            return;
        }
        scheduleAutosave();
    }

    form.addEventListener("input", fieldChanged);
    form.addEventListener("change", fieldChanged);
    if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener("change", updatePreviewMode);
    } else {
        mediaQuery.addListener(updatePreviewMode);
    }

    updatePreviewMode();
})();
