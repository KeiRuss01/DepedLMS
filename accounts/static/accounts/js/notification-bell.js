document.addEventListener("DOMContentLoaded", function () {
    const bell = document.querySelector(".notification-bell");
    const countBadge = document.getElementById("notification-count");

    if (!bell || !countBadge) {
        return;
    }

    const statusUrl = bell.dataset.statusUrl;
    const notificationsUrl = bell.dataset.notificationsUrl;
    const userId = bell.dataset.userId;
    const storageKey = `district1-last-notification-${userId}`;

    let userHasInteracted = false;

    document.addEventListener(
        "pointerdown",
        function () {
            userHasInteracted = true;
        },
        { once: true }
    );

    function playNotificationSound() {
        if (!userHasInteracted) {
            return;
        }

        const AudioContext =
            window.AudioContext || window.webkitAudioContext;

        if (!AudioContext) {
            return;
        }

        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();

        oscillator.frequency.value = 720;
        gain.gain.value = 0.06;

        oscillator.connect(gain);
        gain.connect(context.destination);

        oscillator.start();
        oscillator.stop(context.currentTime + 0.15);
    }

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
        countBadge.textContent = count;

        if (count > 0) {
            countBadge.classList.remove("d-none");
        } else {
            countBadge.classList.add("d-none");
        }
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

                if (data.sound_enabled) {
                    playNotificationSound();
                }

                if (
                    data.vibration_enabled &&
                    "vibrate" in navigator
                ) {
                    navigator.vibrate([120, 60, 120]);
                }
            }
        } catch (error) {
            console.debug(
                "Notification check failed:",
                error
            );
        }
    }

    checkNotifications();

    window.setInterval(
        checkNotifications,
        30000
    );
});