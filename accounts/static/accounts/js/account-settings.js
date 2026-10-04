document.addEventListener("DOMContentLoaded", function () {
    const themeSelect = document.getElementById("id_theme");
    const textSizeSelect = document.getElementById("id_text_size");
    const preferenceForm = document.getElementById("preference-form");

    const originalTheme = document.documentElement.dataset.theme || "light";
    const originalTextSize =
        document.documentElement.dataset.textSize || "default";

    if (themeSelect) {
        themeSelect.addEventListener("change", function () {
            document.documentElement.dataset.theme = this.value;
        });
    }

    if (textSizeSelect) {
        textSizeSelect.addEventListener("change", function () {
            document.documentElement.dataset.textSize = this.value;
        });
    }

    // Restore the saved appearance if the user leaves without saving.
    window.addEventListener("beforeunload", function () {
        if (!preferenceForm || preferenceForm.dataset.submitted === "true") {
            return;
        }

        document.documentElement.dataset.theme = originalTheme;
        document.documentElement.dataset.textSize = originalTextSize;
    });

    if (preferenceForm) {
        preferenceForm.addEventListener("submit", function () {
            preferenceForm.dataset.submitted = "true";
        });
    }
});