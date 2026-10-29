(() => {
    "use strict";

    function localDraftIsNewer(localDraft, serverDraft) {
        if (!localDraft) {
            return false;
        }

        if (["pending", "failed", "syncing"].includes(localDraft.sync_status)) {
            return true;
        }

        const localTime = Date.parse(localDraft.updated_at || "") || 0;
        const serverTime = Date.parse(serverDraft?.server_updated_at || "") || 0;
        return localTime > serverTime;
    }

    async function mergeServerDraft(module, serverDraft) {
        if (!serverDraft || !module.student_id) {
            return null;
        }

        const localId = `${module.student_id}:${module.id}`;
        const localDraft = await window.N1OfflineDB.get(
            "draft_submissions",
            localId
        );

        if (localDraftIsNewer(localDraft, serverDraft)) {
            return localDraft;
        }

        const now = new Date().toISOString();
        const serverPages = (serverDraft.extra_pages || []).map((page) => ({
            ...page,
            local_id: page.local_id || `server-${page.id}`,
            local_only: false,
            sync_status: "synced"
        }));
        const merged = {
            ...(localDraft || {}),
            ...serverDraft,
            local_id: localId,
            module_id: module.id,
            student_id: module.student_id,
            user_id: module.user_id,
            class_id: module.class_id,
            annotations: serverDraft.annotations || [],
            extra_pages: serverPages,
            current_page: serverDraft.current_page || 1,
            status: serverDraft.status || "draft",
            sync_status: "synced",
            sync_error: "",
            created_at: localDraft?.created_at || now,
            updated_at: serverDraft.server_updated_at || now
        };

        await window.N1OfflineDB.put("draft_submissions", merged);
        return merged;
    }

    async function downloadModule(downloadUrl, button) {
        if (!window.N1OfflineDB) {
            throw new Error("The offline database is unavailable.");
        }

        const originalText = button.innerHTML;

        button.disabled = true;
        button.innerHTML = `
            <span class="spinner-border spinner-border-sm me-1"></span>
            Downloading
        `;

        try {
            // Get module information from Django.
            const moduleResponse = await fetch(downloadUrl, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            });

            if (!moduleResponse.ok) {
                throw new Error(
                    `Unable to retrieve module (${moduleResponse.status}).`
                );
            }

            const data = await moduleResponse.json();
            const module = data.module;

            if (!module || !module.id || !module.pdf_url) {
                throw new Error("The module information is incomplete.");
            }

            // Download the private student PDF.
            const pdfResponse = await fetch(module.pdf_url, {
                method: "GET",
                credentials: "same-origin"
            });

            if (!pdfResponse.ok) {
                throw new Error(
                    `Unable to download PDF (${pdfResponse.status}).`
                );
            }

            const pdfBlob = await pdfResponse.blob();

            if (pdfBlob.size === 0) {
                throw new Error("The downloaded PDF is empty.");
            }

            // Save both the module metadata and PDF in IndexedDB.
            await window.N1OfflineDB.put("cached_modules", {
                id: module.id,
                user_id: module.user_id,
                student_id: module.student_id,
                class_id: module.class_id,
                class_name: module.class_name,
                title: module.title,
                instructions: module.instructions,
                week: module.week,
                term: module.term,
                answer_mode: module.answer_mode,
                max_score: module.max_score,
                due_at: module.due_at,
                allow_late: module.allow_late,
                published_at: module.published_at,
                pdf_url: module.pdf_url,
                annotation_save_url: module.annotation_save_url,
                extra_page_create_url: module.extra_page_create_url,
                submit_url: module.submit_url,
                pdf_blob: pdfBlob,
                pdf_type: pdfBlob.type || "application/pdf",
                pdf_size: pdfBlob.size,
                downloaded_at: new Date().toISOString(),
                updated_at: (
                    module.published_at ||
                    new Date().toISOString()
                )
            });

            await mergeServerDraft(module, data.draft);

            button.classList.remove("btn-outline-primary");
            button.classList.add("btn-outline-success");
            button.innerHTML = `
                <i class="bi bi-check-circle me-1"></i>
                Downloaded
            `;

            button.dataset.downloaded = "true";
        } catch (error) {
            console.error("Module download failed:", error);

            button.disabled = false;
            button.innerHTML = originalText;

            alert(
                error.message ||
                "The module could not be downloaded."
            );
        }
    }

    async function updateDownloadButtons() {
        if (!window.N1OfflineDB) {
            return;
        }

        const buttons = document.querySelectorAll(
            "[data-module-download]"
        );

        for (const button of buttons) {
            const moduleId = Number(button.dataset.moduleId);

            if (!moduleId) {
                continue;
            }

            const cachedModule = await window.N1OfflineDB.get(
                "cached_modules",
                moduleId
            );

            if (cachedModule) {
                button.classList.remove("btn-outline-primary");
                button.classList.add("btn-outline-success");
                button.innerHTML = `
                    <i class="bi bi-check-circle me-1"></i>
                    Downloaded
                `;
                button.dataset.downloaded = "true";
            }
        }
    }

    document.addEventListener("click", async (event) => {
        const button = event.target.closest(
            "[data-module-download]"
        );

        if (!button) {
            return;
        }

        event.preventDefault();

        if (!navigator.onLine) {
            alert(
                "Connect to the internet before downloading this module."
            );
            return;
        }

        await downloadModule(
            button.dataset.downloadUrl,
            button
        );
    });

    document.addEventListener("DOMContentLoaded", () => {
        updateDownloadButtons().catch((error) => {
            console.error(
                "Could not check downloaded modules:",
                error
            );
        });
    });

    window.N1ModuleDownloads = {
        download: downloadModule,
        refreshButtons: updateDownloadButtons,
        mergeServerDraft
    };
})();
