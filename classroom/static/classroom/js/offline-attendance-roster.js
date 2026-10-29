(() => {
    "use strict";

    const button = document.getElementById(
        "downloadOfflineRoster"
    );

    const statusText = document.getElementById(
        "offlineRosterStatus"
    );

    if (!button) {
        return;
    }

    function showStatus(message, isError = false) {
        if (!statusText) {
            return;
        }

        statusText.textContent = message;
        statusText.classList.toggle(
            "text-danger",
            isError
        );

        statusText.classList.toggle(
            "text-success",
            !isError && Boolean(message)
        );
    }

    async function removeOldRosterStudents(classId) {
        const existingStudents =
            await window.N1OfflineDB.getAll(
                "cached_students"
            );

        const studentsForClass =
            existingStudents.filter(
                (student) =>
                    Number(student.class_id) ===
                    Number(classId)
            );

        for (const student of studentsForClass) {
            await window.N1OfflineDB.remove(
                "cached_students",
                student.local_id
            );
        }
    }

    async function downloadRoster(options = {}) {
        const automatic = Boolean(options.automatic);

        if (button.disabled) {
            return;
        }

        if (!navigator.onLine) {
            if (!automatic) {
                showStatus(
                    "Connect to the internet before refreshing the roster.",
                    true
                );
            }
            return;
        }

        if (!window.N1OfflineDB) {
            showStatus(
                "The offline database is unavailable.",
                true
            );
            return;
        }

        const classId = Number(
            button.dataset.classId
        );

        if (!classId) {
            showStatus(
                "The class information is missing.",
                true
            );
            return;
        }

        const originalContent = button.innerHTML;

        button.disabled = true;
        button.innerHTML = `
            <span
                class="spinner-border spinner-border-sm me-1"
                aria-hidden="true"
            ></span>
            Updating
        `;

        showStatus(
            automatic
                ? "Updating the offline attendance roster automatically…"
                : ""
        );

        try {
            await window.N1OfflineDB.open();

            const response = await fetch(
                button.dataset.rosterUrl,
                {
                    method: "GET",
                    credentials: "same-origin",
                    headers: {
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    cache: "no-store",
                }
            );

            const contentType =
                response.headers.get("Content-Type") || "";

            const data = contentType.includes(
                "application/json"
            )
                ? await response.json()
                : null;

            if (!response.ok) {
                throw new Error(
                    data?.error ||
                    `Roster download failed (${response.status}).`
                );
            }

            if (
                !data?.classroom ||
                !Array.isArray(data.students)
            ) {
                throw new Error(
                    "The roster response is incomplete."
                );
            }

            await removeOldRosterStudents(classId);

            await window.N1OfflineDB.put(
                "cached_classes",
                {
                    ...data.classroom,
                    attendance_statuses:
                        data.attendance_statuses || [],
                    day_types:
                        data.day_types || [],
                    downloaded_at:
                        data.downloaded_at,
                    updated_at:
                        new Date().toISOString(),
                }
            );

            for (const student of data.students) {
                await window.N1OfflineDB.put(
                    "cached_students",
                    {
                        ...student,
                        local_id:
                            `${classId}:${student.student_id}`,
                        class_id: classId,
                        updated_at:
                            new Date().toISOString(),
                    }
                );
            }

            await window.N1OfflineDB.put(
                "sync_metadata",
                {
                    key: `attendance_roster:${classId}`,
                    class_id: classId,
                    record_count:
                        data.students.length,
                    last_pulled_at:
                        new Date().toISOString(),
                }
            );

            button.classList.remove(
                "btn-outline-primary"
            );

            button.classList.add(
                "btn-outline-success"
            );

            button.innerHTML = `
                <i class="bi bi-check-circle me-1"></i>
                Offline Roster Ready
            `;

            showStatus(
                `${data.students.length} learner records saved on this device.`
            );
        } catch (error) {
            console.error(
                "Offline roster download failed:",
                error
            );

            button.innerHTML = originalContent;

            showStatus(
                error.message ||
                "The roster could not be downloaded.",
                true
            );
        } finally {
            button.disabled = false;
        }
    }

    button.addEventListener(
        "click",
        () => downloadRoster()
    );

    window.addEventListener(
        "load",
        () => downloadRoster({automatic: true})
    );
})();
