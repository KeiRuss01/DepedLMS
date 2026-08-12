document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("svSidebarToggle");
    const body = document.body;

    if (!toggleBtn) return;

    toggleBtn.addEventListener("click", function () {
        if (window.innerWidth <= 991) {
            body.classList.toggle("sv-sidebar-open");
        } else {
            body.classList.toggle("sv-sidebar-collapsed");
        }
    });
});
