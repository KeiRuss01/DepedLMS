(() => {
    "use strict";

    const button = document.getElementById("downloadOfflineGradebook");
    const statusText = document.getElementById("offlineGradebookStatus");

    if (!button) return;

    function showStatus(message, isError = false) {
        if (!statusText) return;
        statusText.textContent = message;
        statusText.classList.toggle("text-danger", isError);
        statusText.classList.toggle("text-success", !isError && Boolean(message));
    }

    async function removeOldItems(classId, term) {
        const records = await window.N1OfflineDB.getAll("cached_grade_items");
        for (const record of records) {
            if (Number(record.class_id) === classId && String(record.term) === term) {
                if (record.offline_pending) continue;
                await window.N1OfflineDB.remove("cached_grade_items", record.local_id);
            }
        }
    }

    async function removeOldSyncedScores(classId, term) {
        const records = await window.N1OfflineDB.getAll("cached_score");
        for (const record of records) {
            if (
                Number(record.class_id) === classId &&
                String(record.term) === term &&
                record.sync_status === "synced"
            ) {
                await window.N1OfflineDB.remove("cached_score", record.local_id);
            }
        }
    }

    async function downloadGradebook(options = {}) {
        const automatic = Boolean(options.automatic);

        if (button.disabled) return;

        if (!navigator.onLine) {
            if (!automatic) {
                showStatus("Connect to the internet before refreshing the offline copy.", true);
            }
            return;
        }

        const classId = Number(button.dataset.classId);
        const term = String(button.dataset.term || "1");
        const originalContent = button.innerHTML;

        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Updating';
        showStatus(automatic ? "Updating the offline gradebook automatically…" : "");

        try {
            await window.N1OfflineDB.open();

            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 30000);

            let response;
            try {
                response = await fetch(
                    `${button.dataset.downloadUrl}?term=${encodeURIComponent(term)}`,
                    {
                        credentials: "same-origin",
                        headers: {
                            Accept: "application/json",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        cache: "no-store",
                        signal: controller.signal,
                    }
                );
            } finally {
                clearTimeout(timeout);
            }

            const data = await response.json();
            if (!response.ok) throw new Error(data.error || `Download failed (${response.status}).`);

            await removeOldItems(classId, term);
            await removeOldSyncedScores(classId, term);

            const existingClass = await window.N1OfflineDB.get("cached_classes", classId) || {};
            await window.N1OfflineDB.put("cached_classes", {
                ...existingClass,
                ...data.classroom,
                gradebook_settings: data.settings,
                gradebook_locked: Boolean(data.report_locked),
                gradebook_downloaded_at: data.downloaded_at,
                updated_at: new Date().toISOString(),
            });

            for (const student of data.students || []) {
                await window.N1OfflineDB.put("cached_students", {
                    ...student,
                    local_id: `${classId}:${student.student_id}`,
                    class_id: classId,
                    updated_at: new Date().toISOString(),
                });
            }

            const itemMap = new Map();
            for (const item of data.items || []) {
                itemMap.set(Number(item.item_id), item);
                await window.N1OfflineDB.put("cached_grade_items", {
                    ...item,
                    local_id: `${classId}:${term}:${item.item_id}`,
                    class_id: classId,
                    updated_at: new Date().toISOString(),
                });
            }

            for (const score of data.scores || []) {
                const localId = `grade:${classId}:${term}:${score.item_id}:${score.student_id}`;
                const existing = await window.N1OfflineDB.get("cached_score", localId);

                if (existing && ["pending", "failed"].includes(existing.sync_status)) continue;

                const item = itemMap.get(Number(score.item_id));
                await window.N1OfflineDB.put("cached_score", {
                    local_id: localId,
                    class_id: classId,
                    term,
                    grade_item_id: Number(score.item_id),
                    student_id: Number(score.student_id),
                    module_id: item?.module_id || null,
                    score: score.score === null ? null : Number(score.score),
                    highest_possible_score: Number(item?.highest_possible_score || 0),
                    sync_status: "synced",
                    sync_error: "",
                    server_updated_at: score.server_updated_at,
                    local_updated_at: new Date().toISOString(),
                });
            }

            await window.N1OfflineDB.put("sync_metadata", {
                key: `gradebook:${classId}:${term}`,
                class_id: classId,
                term,
                last_pulled_at: new Date().toISOString(),
                item_count: (data.items || []).length,
                student_count: (data.students || []).length,
            });

            button.innerHTML = '<i class="bi bi-check-circle"></i> Offline Gradebook Ready';
            showStatus(`Term ${term} gradebook saved on this device.`);
        } catch (error) {
            console.error("Offline gradebook download failed:", error);
            button.innerHTML = originalContent;
            showStatus(error.message || "The gradebook could not be downloaded.", true);
        } finally {
            button.disabled = false;
        }
    }

    button.addEventListener("click", () => downloadGradebook());
    window.addEventListener("load", () => downloadGradebook({automatic:true}));
})();
