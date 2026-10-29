/* Apply the saved account theme before paint; reuse it in cached offline pages. */
(() => {
    "use strict";
    const root = document.documentElement;
    const storageKey = "n1-saved-theme";
    let theme = root.dataset.theme;
    try {
        if (theme === "light" || theme === "dark") {
            localStorage.setItem(storageKey, theme);
        } else {
            theme = localStorage.getItem(storageKey);
        }
    } catch (_) {
        // Appearance remains available when browser storage is restricted.
    }
    root.dataset.theme = theme === "dark" ? "dark" : "light";
    root.dataset.bsTheme = root.dataset.theme;
    new MutationObserver(() => {
        root.dataset.bsTheme = root.dataset.theme === "dark" ? "dark" : "light";
    }).observe(root, {attributes: true, attributeFilter: ["data-theme"]});
})();
