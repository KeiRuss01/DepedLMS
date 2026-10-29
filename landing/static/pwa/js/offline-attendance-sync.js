(() => {
    "use strict";

    let synchronizationPromise = null;

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

    async function requestJson(url, options = {}) {
        if (!url) {
            throw new Error(
                "The attendance synchronization URL is missing. Download the roster again."
            );
        }

        const response = await fetch(
            url,
            {
                credentials: "same-origin",
                ...options,
                headers: {
                    "X-CSRFToken":
                        getCookie("csrftoken"),
                    "X-Requested-With":
                        "XMLHttpRequest",
                    ...(options.headers || {}),
                },
            }
        );

        const contentType =
            response.headers.get("Content-Type") || "";

        const data = contentType.includes(
            "application/json"
        )
            ? await response.json()
            : null;

        if (
            response.redirected &&
            response.url.includes("/accounts/login")
        ) {
            throw new Error(
                "Sign in again before synchronizing attendance."
            );
        }

        if (!response.ok) {
            throw new Error(
                data?.error ||
                `Attendance synchronization failed (${response.status}).`
            );
        }

        if (!data) {
            throw new Error(
                "The server returned an unexpected response."
            );
        }

        return data;
    }

    async function attendanceRecords(
        classId,
        attendanceDate
    ) {
        const records =
            await window.N1OfflineDB.getAll(
                "cached_attendance"
            );

        return records.filter((record) => (
            Number(record.class_id) ===
                Number(classId) &&
            record.attendance_date ===
                attendanceDate
        ));
    }

    async function markRecords(
        records,
        syncStatus,
        extraValues = {}
    ) {
        for (const record of records) {
            await window.N1OfflineDB.put(
                "cached_attendance",
                {
                    ...record,
                    ...extraValues,
                    sync_status: syncStatus,
                    updated_at:
                        new Date().toISOString(),
                }
            );
        }
    }

    async function registeredDevice() {
        if (window.N1DeviceRegistry) {
            await window.N1DeviceRegistry.register();
        }

        const identity =
            await window.N1OfflineDB.get(
                "device_identity",
                "current"
            );

        if (!identity?.device_id) {
            throw new Error(
                "This device has not been registered."
            );
        }

        return identity;
    }

    async function syncAttendanceItem(queueItem) {
        const classId =
            Number(queueItem.class_id);

        const attendanceDate =
            queueItem.attendance_date;

        const cachedClass =
            await window.N1OfflineDB.get(
                "cached_classes",
                classId
            );

        if (!cachedClass) {
            throw new Error(
                "The cached class information could not be found."
            );
        }

        const records =
            await attendanceRecords(
                classId,
                attendanceDate
            );

        const dayRecord = records.find(
            (record) =>
                record.record_type === "day"
        );

        if (!dayRecord) {
            throw new Error(
                "The offline attendance day could not be found."
            );
        }

        const studentRecords = records.filter(
            (record) =>
                record.record_type === "student"
        );

        const identity =
            await registeredDevice();

        await markRecords(
            records,
            "syncing"
        );

        const result = await requestJson(
            cachedClass.attendance_sync_url,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    device_id:
                        identity.device_id,
                    attendance_date:
                        attendanceDate,
                    day_type:
                        dayRecord.day_type,
                    note:
                        dayRecord.note || "",
                    client_updated_at:
                        dayRecord.updated_at,
                    records:
                        studentRecords.map(
                            (record) => ({
                                student_id:
                                    record.student_id,
                                status:
                                    record.status,
                                remarks:
                                    record.remarks || "",
                            })
                        ),
                }),
            }
        );

        await markRecords(
            records,
            "synced",
            {
                server_updated_at:
                    result.server_updated_at,
                sync_error: "",
            }
        );

        await window.N1OfflineDB.put(
            "sync_metadata",
            {
                key:
                    `attendance:${classId}:${attendanceDate}`,
                class_id: classId,
                attendance_date:
                    attendanceDate,
                last_pushed_at:
                    new Date().toISOString(),
                server_updated_at:
                    result.server_updated_at,
            }
        );

        await window.N1OfflineDB.remove(
            "offline_queue",
            queueItem.queue_id
        );

        window.dispatchEvent(
            new CustomEvent(
                "n1:attendance-sync",
                {
                    detail: {
                        status: "completed",
                        classId,
                        attendanceDate,
                        result,
                    },
                }
            )
        );
    }

    async function markFailure(
        queueItem,
        error
    ) {
        const records =
            await attendanceRecords(
                queueItem.class_id,
                queueItem.attendance_date
            );

        const errorMessage =
            error.message ||
            "Attendance synchronization failed.";

        await markRecords(
            records,
            "failed",
            {
                sync_error: errorMessage,
            }
        );

        queueItem.status = "failed";
        queueItem.retry_count =
            Number(queueItem.retry_count || 0) + 1;
        queueItem.error_message =
            errorMessage;
        queueItem.updated_at =
            new Date().toISOString();

        await window.N1OfflineDB.put(
            "offline_queue",
            queueItem
        );

        window.dispatchEvent(
            new CustomEvent(
                "n1:attendance-sync",
                {
                    detail: {
                        status: "failed",
                        classId:
                            Number(queueItem.class_id),
                        attendanceDate:
                            queueItem.attendance_date,
                        message:
                            errorMessage,
                    },
                }
            )
        );
    }

    async function runSynchronization() {
        if (
            !navigator.onLine ||
            !window.N1OfflineDB
        ) {
            return {
                synchronized: 0,
                failed: 0,
            };
        }

        await window.N1OfflineDB.open();

        const queue =
            await window.N1OfflineDB.getAll(
                "offline_queue"
            );

        const pendingItems = queue.filter(
            (item) => (
                item.action_type ===
                    "attendance_sync" &&
                ["pending", "failed"].includes(
                    item.status
                )
            )
        );

        let synchronized = 0;
        let failed = 0;

        for (const item of pendingItems) {
            item.status = "syncing";
            item.error_message = "";
            item.updated_at =
                new Date().toISOString();

            await window.N1OfflineDB.put(
                "offline_queue",
                item
            );

            try {
                await syncAttendanceItem(item);
                synchronized += 1;
            } catch (error) {
                console.error(
                    "Attendance synchronization failed:",
                    error
                );

                await markFailure(
                    item,
                    error
                );

                failed += 1;
            }
        }

        return {
            synchronized,
            failed,
        };
    }

    function synchronizeNow() {
        if (!synchronizationPromise) {
            synchronizationPromise =
                runSynchronization()
                    .finally(() => {
                        synchronizationPromise = null;
                    });
        }

        return synchronizationPromise;
    }

    window.N1AttendanceSync = {
        syncNow: synchronizeNow,
    };

    window.addEventListener(
        "online",
        synchronizeNow
    );

    document.addEventListener(
        "DOMContentLoaded",
        synchronizeNow
    );
})();