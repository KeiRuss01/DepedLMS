(() => {
    "use strict";

    const DEVICE_KEY = "current";

    function getCookie(name) {
        const prefix = `${name}=`;

        const item = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith(prefix));

        return item
            ? decodeURIComponent(item.slice(prefix.length))
            : "";
    }

    function detectDeviceType() {
        const userAgent = navigator.userAgent.toLowerCase();

        if (/ipad|tablet/.test(userAgent)) {
            return "tablet";
        }

        if (/android|iphone|mobile/.test(userAgent)) {
            return "mobile";
        }

        return "desktop";
    }

    function detectBrowser() {
        const userAgent = navigator.userAgent;

        if (userAgent.includes("Edg/")) {
            return "Microsoft Edge";
        }

        if (
            userAgent.includes("Chrome/") &&
            !userAgent.includes("Edg/")
        ) {
            return "Google Chrome";
        }

        if (userAgent.includes("Firefox/")) {
            return "Mozilla Firefox";
        }

        if (
            userAgent.includes("Safari/") &&
            !userAgent.includes("Chrome/")
        ) {
            return "Safari";
        }

        return "Unknown browser";
    }

    function createDeviceName(deviceType, browser) {
        const platform =
            navigator.userAgentData?.platform ||
            navigator.platform ||
            "Unknown platform";

        return `${platform} ${deviceType} — ${browser}`;
    }

    async function getDeviceIdentity() {
        if (!window.N1OfflineDB) {
            throw new Error(
                "The offline database is unavailable."
            );
        }

        await window.N1OfflineDB.open();

        let identity = await window.N1OfflineDB.get(
            "device_identity",
            DEVICE_KEY
        );

        if (!identity) {
            const deviceType = detectDeviceType();
            const browser = detectBrowser();

            identity = {
                key: DEVICE_KEY,
                device_id: crypto.randomUUID(),
                device_name: createDeviceName(
                    deviceType,
                    browser
                ),
                device_type: deviceType,
                browser,
                created_at: new Date().toISOString(),
                registered: false,
            };

            await window.N1OfflineDB.put(
                "device_identity",
                identity
            );
        }

        return identity;
    }

    async function registerDevice() {
        if (!navigator.onLine) {
            return null;
        }

        const identity = await getDeviceIdentity();

        const response = await fetch(
            "/pwa/devices/register/",
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-CSRFToken": getCookie("csrftoken"),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({
                    device_id: identity.device_id,
                    device_name: identity.device_name,
                    device_type: identity.device_type,
                    browser: identity.browser,
                }),
            }
        );

        const contentType =
            response.headers.get("Content-Type") || "";

        const data = contentType.includes("application/json")
            ? await response.json()
            : null;

        if (
            response.redirected &&
            response.url.includes("/accounts/login")
        ) {
            return null;
        }

        if (!response.ok) {
            throw new Error(
                data?.error ||
                `Device registration failed (${response.status}).`
            );
        }

        identity.registered = true;
        identity.registered_at =
            identity.registered_at ||
            new Date().toISOString();
        identity.last_registered_at =
            new Date().toISOString();
        identity.user_id = data.account?.user_id || identity.user_id || null;
        identity.account_name = data.account?.full_name || identity.account_name || "";
        identity.account_role = data.account?.role || identity.account_role || "";
        identity.account_role_label = data.account?.role_label || identity.account_role_label || "";

        await window.N1OfflineDB.put(
            "device_identity",
            identity
        );

        window.dispatchEvent(
            new CustomEvent("n1:device-registered", {
                detail: data.device,
            })
        );

        return data.device;
    }

    function startRegistration() {
        registerDevice().catch((error) => {
            console.error(
                "Device registration failed:",
                error
            );
        });
    }

    document.addEventListener(
        "DOMContentLoaded",
        startRegistration
    );

    window.addEventListener(
        "online",
        startRegistration
    );

    window.N1DeviceRegistry = {
        getIdentity: getDeviceIdentity,
        register: registerDevice,
    };
})();
