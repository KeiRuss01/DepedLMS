document.addEventListener("DOMContentLoaded", function () {
    const bell = document.querySelector(".notification-bell");

    const countBadges = document.querySelectorAll(
        "[data-notification-count]"
    );

    if (!bell || countBadges.length === 0) {
        return;
    }

    const statusUrl = bell.dataset.statusUrl;
    const notificationsUrl = bell.dataset.notificationsUrl;
    const userId = bell.dataset.userId;
    const storageKey = `north1-last-notification-${userId}`;

    function showToast(title, message) {
        const existingToast = document.querySelector(
            ".notification-live-toast"
        );

        if (existingToast) {
            existingToast.remove();
        }

        const toast = document.createElement("a");

        toast.href = notificationsUrl;
        toast.className = "notification-live-toast";
        toast.innerHTML = `
            <strong>${escapeHtml(title)}</strong>
            <span>${escapeHtml(message)}</span>
        `;

        document.body.appendChild(toast);

        window.setTimeout(function () {
            toast.remove();
        }, 6000);
    }

    function escapeHtml(value) {
        const element = document.createElement("div");
        element.textContent = value || "";
        return element.innerHTML;
    }

    function updateBadge(count) {
        countBadges.forEach((badge) => {
            badge.textContent = count > 99 ? "99+" : count;

            if (count > 0) {
                badge.classList.remove("d-none");
            } else {
                badge.classList.add("d-none");
            }
        });
    }

    async function checkNotifications() {
        try {
            const response = await fetch(statusUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                cache: "no-store",
            });

            if (!response.ok) {
                return;
            }

            const data = await response.json();

            updateBadge(data.unread_count);

            if (!data.latest_id) {
                return;
            }

            const previousId = Number(
                sessionStorage.getItem(storageKey) || 0
            );

            const currentId = Number(data.latest_id);

            if (previousId === 0) {
                sessionStorage.setItem(storageKey, currentId);
                return;
            }

            if (currentId > previousId) {
                sessionStorage.setItem(storageKey, currentId);

                showToast(
                    data.latest_title,
                    data.latest_message
                );

            }
        } catch (error) {
            console.debug(
                "Notification check failed:",
                error
            );
        }
    }

    checkNotifications();

    // Keep the in-app alert responsive during live classroom activity.
    window.setInterval(checkNotifications, 10000);
});
