(() => {
    "use strict";

    let syncPromise = null;

    function cookie(name) {
        const prefix = `${name}=`;
        const value = document.cookie
            .split(";")
            .map((item) => item.trim())
            .find((item) => item.startsWith(prefix));
        return value ? decodeURIComponent(value.slice(prefix.length)) : "";
    }

    async function requestJson(url, options = {}) {
        if (!url) {
            throw new Error(
                "This downloaded module is missing synchronization URLs. Download it again."
            );
        }

        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 30000);

        let response;
        try {
            response = await fetch(url, {
                credentials: "same-origin",
                ...options,
                signal: controller.signal,
                headers: {
                    "X-CSRFToken": cookie("csrftoken"),
                    "X-Requested-With": "XMLHttpRequest",
                    ...(options.headers || {})
                }
            });
        } catch (error) {
            if (error.name === "AbortError") {
                throw new Error(`Synchronization timed out while contacting ${url}.`);
            }
            throw error;
        } finally {
            window.clearTimeout(timeout);
        }

        const contentType = response.headers.get("Content-Type") || "";
        const data = contentType.includes("application/json")
            ? await response.json()
            : null;

        if (
            response.redirected &&
            response.url.includes("/accounts/login")
        ) {
            throw new Error("Sign in again before synchronizing offline work.");
        }

        if (!response.ok) {
            throw new Error(
                data?.error || `Synchronization failed (${response.status}).`
            );
        }

        if (!data) {
            throw new Error("The server returned an unexpected response.");
        }

        return data;
    }

    async function saveDraft(draft) {
        draft.updated_at = new Date().toISOString();
        await window.N1OfflineDB.put("draft_submissions", draft);
    }

    async function createServerExtraPage(module, draft, page, pageIndex) {
        const formData = new FormData();
        formData.append("page_type", page.page_type);
        formData.append("title", page.title || "Answer Page");
        formData.append(
            "related_pdf_page",
            String(page.related_pdf_page || page.related_module_page || draft.current_page || 1)
        );
        formData.append("caption", page.caption || "");

        if (page.page_type === "upload") {
            if (!page.uploaded_blob) {
                throw new Error(`The file for "${page.title}" is missing.`);
            }

            formData.append(
                "file",
                page.uploaded_blob,
                page.uploaded_file_name ||
                    page.original_name ||
                    page.title ||
                    "offline-upload"
            );
        }

        const created = await requestJson(
            module.extra_page_create_url,
            {
                method: "POST",
                body: formData
            }
        );

        let serverPage = created.page;

        if (["essay", "drawing"].includes(page.page_type)) {
            const updated = await requestJson(
                serverPage.update_url,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        title: page.title,
                        caption: page.caption || "",
                        related_pdf_page: page.related_pdf_page,
                        essay_text: page.essay_text || "",
                        essay_html: page.essay_html || "",
                        essay_font_size: page.essay_font_size || 16,
                        essay_bold: Boolean(page.essay_bold),
                        essay_italic: Boolean(page.essay_italic),
                        drawing_data: page.drawing_data || []
                    })
                }
            );
            serverPage = updated.page;
        }

        draft.extra_pages[pageIndex] = {
            ...serverPage,
            local_id: page.local_id || page.id,
            local_only: false,
            sync_status: "synced"
        };
        await saveDraft(draft);
    }

    async function updateServerExtraPage(draft, page, pageIndex) {
        if (!page.update_url) {
            return;
        }

        const updated = await requestJson(page.update_url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                title: page.title,
                caption: page.caption || "",
                related_pdf_page: page.related_pdf_page,
                essay_text: page.essay_text || "",
                essay_html: page.essay_html || "",
                essay_font_size: page.essay_font_size || 16,
                essay_bold: Boolean(page.essay_bold),
                essay_italic: Boolean(page.essay_italic),
                drawing_data: page.drawing_data || []
            })
        });

        draft.extra_pages[pageIndex] = {
            ...page,
            ...updated.page,
            local_only: false,
            sync_status: "synced"
        };
        await saveDraft(draft);
    }

    async function syncDraftContent(queueItem) {
        const draft = await window.N1OfflineDB.get(
            "draft_submissions",
            queueItem.draft_local_id
        );
        if (!draft) {
            throw new Error("The saved draft could not be found on this device.");
        }

        const module = await window.N1OfflineDB.get(
            "cached_modules",
            Number(draft.module_id)
        );
        if (!module) {
            throw new Error("The downloaded module could not be found.");
        }

        draft.sync_status = "syncing";
        draft.sync_stage = "saving annotations";
        draft.sync_error = "";
        await saveDraft(draft);

        await requestJson(module.annotation_save_url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                current_page: draft.current_page || 1,
                annotations: draft.annotations || []
            })
        });

        draft.extra_pages = Array.isArray(draft.extra_pages)
            ? draft.extra_pages
            : [];

        const deletedPages = Array.isArray(draft.deleted_extra_pages)
            ? draft.deleted_extra_pages
            : [];
        for (const deletedPage of deletedPages) {
            if (deletedPage.delete_url) {
                await requestJson(deletedPage.delete_url, { method: "POST" });
            }
        }
        draft.deleted_extra_pages = [];

        for (let index = 0; index < draft.extra_pages.length; index += 1) {
            const page = draft.extra_pages[index];
            draft.sync_stage = `saving answer page ${index + 1}`;
            await saveDraft(draft);

            if (page.local_only === true || !page.id || !page.update_url) {
                await createServerExtraPage(module, draft, page, index);
            } else if (page.sync_status !== "synced") {
                await updateServerExtraPage(draft, page, index);
            }
        }

        draft.status = draft.status === "queued" ? "queued" : "draft";
        draft.sync_status = "synced";
        draft.sync_stage = "";
        draft.sync_error = "";
        draft.server_updated_at = new Date().toISOString();
        await saveDraft(draft);

        return { draft, module };
    }

    async function syncModuleSubmission(queueItem) {
        const { draft, module } = await syncDraftContent(queueItem);

        draft.sync_stage = "building final PDF";
        await saveDraft(draft);
        const result = await requestJson(module.submit_url, {
            method: "POST"
        });

        draft.status = "submitted";
        draft.sync_status = "synced";
        draft.submission_id = result.submission_id;
        draft.submitted_at = result.submitted_at;
        await saveDraft(draft);

        await window.N1OfflineDB.remove(
            "offline_queue",
            queueItem.queue_id
        );

        window.dispatchEvent(new CustomEvent("n1:offline-sync", {
            detail: {
                status: "completed",
                moduleId: Number(draft.module_id),
                draftLocalId: draft.local_id,
                submissionId: result.submission_id
            }
        }));
    }

    async function syncModuleDraft(queueItem) {
        const { draft } = await syncDraftContent(queueItem);

        await window.N1OfflineDB.remove(
            "offline_queue",
            queueItem.queue_id
        );

        window.dispatchEvent(new CustomEvent("n1:offline-sync", {
            detail: {
                status: "draft-synced",
                moduleId: Number(draft.module_id),
                draftLocalId: draft.local_id
            }
        }));
    }

    async function runSync() {
        if (!navigator.onLine || !window.N1OfflineDB) {
            return { synced: 0, failed: 0 };
        }

        await window.N1OfflineDB.open();

        const queue = await window.N1OfflineDB.getAll("offline_queue");

        /*
        * A page refresh may leave records marked as "syncing".
        * Reset them because no previous JavaScript process is still handling them.
        */
        for (const item of queue) {
            if (
                ["module_submission", "module_draft_sync"].includes(item.action_type) &&
                item.status === "syncing"
            ) {
                item.status = "pending";
                item.error_message = "";
                item.updated_at = new Date().toISOString();

                await window.N1OfflineDB.put(
                    "offline_queue",
                    item
                );
            }
        }

        const refreshedQueue = await window.N1OfflineDB.getAll(
            "offline_queue"
        );

        const pending = refreshedQueue.filter((item) => (
            ["module_submission", "module_draft_sync"].includes(item.action_type) &&
            ["pending", "failed"].includes(item.status)
        ));

        let synced = 0;
        let failed = 0;

        for (const item of pending) {
            item.status = "syncing";
            item.error_message = "";
            item.updated_at = new Date().toISOString();

            await window.N1OfflineDB.put(
                "offline_queue",
                item
            );

            try {
                if (item.action_type === "module_submission") {
                    await syncModuleSubmission(item);
                } else {
                    await syncModuleDraft(item);
                }
                synced += 1;
            } catch (error) {
                failed += 1;

                item.status = "failed";
                item.retry_count =
                    Number(item.retry_count || 0) + 1;
                item.error_message =
                    error.message || "Synchronization failed.";
                item.synced_at = null;
                item.updated_at = new Date().toISOString();

                await window.N1OfflineDB.put(
                    "offline_queue",
                    item
                );

                const failedDraft =
                    await window.N1OfflineDB.get(
                        "draft_submissions",
                        item.draft_local_id
                    );

                if (failedDraft) {
                    if (item.action_type === "module_submission") {
                        failedDraft.status = "queued";
                    }
                    failedDraft.sync_status = "failed";
                    failedDraft.sync_error = `${
                        failedDraft.sync_stage ||
                        "synchronization"
                    }: ${item.error_message}`;
                    failedDraft.updated_at =
                        new Date().toISOString();

                    await window.N1OfflineDB.put(
                        "draft_submissions",
                        failedDraft
                    );
                }

                window.dispatchEvent(
                    new CustomEvent("n1:offline-sync", {
                        detail: {
                            status: "failed",
                            moduleId: Number(item.target_id),
                            draftLocalId: item.draft_local_id,
                            message: item.error_message
                        }
                    })
                );
            }
        }

        return { synced, failed };
    }

    function syncNow() {
        if (syncPromise) {
            return syncPromise;
        }

        syncPromise = runSync()
            .catch((error) => {
                console.error(
                    "Offline synchronization failed:",
                    error
                );

                return {
                    synced: 0,
                    failed: 1,
                    error: error.message
                };
            })
            .finally(() => {
                syncPromise = null;
            });

        return syncPromise;
    }

    window.N1OfflineSync = {
        syncNow
    };

    /*
    * Automatically synchronize when internet returns.
    */
    window.addEventListener("online", () => {
        window.setTimeout(() => {
            syncNow();
        }, 1000);
    });

    /*
    * Also check unfinished work when the application opens online.
    */
    document.addEventListener("DOMContentLoaded", () => {
        if (navigator.onLine) {
            window.setTimeout(() => {
                syncNow();
            }, 1500);
        }
    });

})();
