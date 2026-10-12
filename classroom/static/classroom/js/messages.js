const messagePanelTrigger = document.getElementById("messagePanelTrigger");
const messagePanel = document.getElementById("messageFloatingPanel");
const messagePanelClose = document.getElementById("messagePanelClose");
const messagePanelList = document.getElementById("messagePanelList");
const messagePanelChat = document.getElementById("messagePanelChat");

function scrollMessageThreads() {
    document.querySelectorAll("#conversationMessages, [data-panel-thread]").forEach((thread) => {
        thread.scrollTop = thread.scrollHeight;
    });
}

function initializeMessageSearch(scope = document) {
    scope.querySelectorAll("[data-message-search]").forEach((input) => {
        if (input.dataset.ready) return;
        input.dataset.ready = "true";
        input.addEventListener("input", () => {
            const query = input.value.trim().toLowerCase();
            const list = input.closest(".message-panel-list, .messages-card")?.querySelector("[data-message-list]");
            list?.querySelectorAll("[data-message-name]").forEach((row) => {
                row.hidden = !row.dataset.messageName.toLowerCase().includes(query);
            });
        });
    });
}

async function loadPanelConversation(url) {
    if (!messagePanelChat || !messagePanelList) return;
    messagePanelChat.hidden = false;
    messagePanelList.hidden = true;
    messagePanelChat.innerHTML = '<div class="message-panel-empty"><span class="spinner-border text-primary"></span><span>Loading conversation…</span></div>';
    try {
        const response = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (!response.ok) throw new Error("Conversation could not be loaded.");
        messagePanelChat.innerHTML = await response.text();
        bindPanelChat(url);
        scrollMessageThreads();
    } catch (error) {
        messagePanelChat.innerHTML = '<div class="message-panel-empty"><i class="bi bi-exclamation-circle"></i><strong>Conversation unavailable</strong></div>';
    }
}

function bindPanelChat(panelUrl) {
    messagePanelChat?.querySelector("[data-message-panel-back]")?.addEventListener("click", () => {
        messagePanelChat.hidden = true;
        messagePanelList.hidden = false;
    });

    const form = messagePanelChat?.querySelector("[data-panel-message-form]");
    form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("button");
        button.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            const result = await response.json();
            if (!response.ok || !result.ok) throw new Error(result.error || "Message not sent.");
            await loadPanelConversation(result.panel_url || panelUrl);
        } catch (error) {
            button.disabled = false;
            alert(error.message);
        }
    });
}

document.querySelectorAll(".message-panel-conversations [data-panel-url]").forEach((link) => {
    link.addEventListener("click", (event) => {
        if (window.innerWidth <= 991) return;
        event.preventDefault();
        loadPanelConversation(link.dataset.panelUrl);
    });
});

messagePanelTrigger?.addEventListener("click", () => {
    const willOpen = messagePanel.hidden;
    messagePanel.hidden = !willOpen;
    messagePanelTrigger.setAttribute("aria-expanded", String(willOpen));
    if (willOpen) {
        messagePanelList.hidden = false;
        messagePanelChat.hidden = true;
    }
});

messagePanelClose?.addEventListener("click", () => {
    messagePanel.hidden = true;
    messagePanelTrigger?.setAttribute("aria-expanded", "false");
});

document.addEventListener("click", (event) => {
    if (!messagePanel || messagePanel.hidden) return;
    if (!messagePanel.contains(event.target) && !messagePanelTrigger?.contains(event.target)) {
        messagePanel.hidden = true;
        messagePanelTrigger?.setAttribute("aria-expanded", "false");
    }
});

initializeMessageSearch();
scrollMessageThreads();
