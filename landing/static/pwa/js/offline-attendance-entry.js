(() => {
    "use strict";

    const parameters = new URLSearchParams(
        window.location.search
    );

    const classId = Number(
        parameters.get("class")
    );

    const app = document.getElementById(
        "offlineAttendanceApp"
    );

    const errorSection = document.getElementById(
        "offlineAttendanceError"
    );

    const errorText = document.getElementById(
        "offlineAttendanceErrorText"
    );

    const className = document.getElementById(
        "offlineClassName"
    );

    const classDetails = document.getElementById(
        "offlineClassDetails"
    );

    const rosterCount = document.getElementById(
        "rosterCount"
    );

    const rowsContainer = document.getElementById(
        "offlineAttendanceRows"
    );

    const dateInput = document.getElementById(
        "offlineAttendanceDate"
    );

    const noteInput = document.getElementById(
        "offlineDayNote"
    );

    const form = document.getElementById(
        "offlineAttendanceForm"
    );

    const message = document.getElementById(
        "offlineAttendanceMessage"
    );

    const connectionStatus = document.getElementById(
        "connectionStatus"
    );

    const nonClassMessage = document.getElementById(
        "nonClassDayMessage"
    );

    let cachedClass = null;
    let cachedStudents = [];

    function localToday() {
        const currentDate = new Date();

        currentDate.setMinutes(
            currentDate.getMinutes() -
            currentDate.getTimezoneOffset()
        );

        return currentDate
            .toISOString()
            .slice(0, 10);
    }

    function showError(errorMessage) {
        app.hidden = true;
        errorSection.hidden = false;
        errorText.textContent = errorMessage;
    }

    function showMessage(text, isError = false) {
        message.textContent = text;

        message.classList.toggle(
            "text-danger",
            isError
        );

        message.classList.toggle(
            "text-success",
            !isError
        );
    }

    function updateConnectionStatus() {
        const online = navigator.onLine;

        connectionStatus.textContent = online
            ? "Online"
            : "Offline";

        connectionStatus.classList.toggle(
            "offline",
            !online
        );
    }

    function selectedDayType() {
        return (
            document.querySelector(
                'input[name="offline_day_type"]:checked'
            )?.value || "class_day"
        );
    }

    function statusChoices() {
        if (
            Array.isArray(
                cachedClass.attendance_statuses
            ) &&
            cachedClass.attendance_statuses.length
        ) {
            return cachedClass.attendance_statuses;
        }

        return [
            { value: "present", label: "Present" },
            { value: "absent", label: "Absent" },
            { value: "late", label: "Late" },
            { value: "excused", label: "Excused" },
        ];
    }

    function createStatusSelect(student) {
        const select = document.createElement("select");

        select.className =
            "form-select offline-student-status";

        select.dataset.studentId =
            String(student.student_id);

        for (const choice of statusChoices()) {
            const option =
                document.createElement("option");

            option.value = choice.value;
            option.textContent = choice.label;

            select.appendChild(option);
        }

        return select;
    }

    function renderStudents() {
        rowsContainer.replaceChildren();

        cachedStudents.forEach((student, index) => {
            const row = document.createElement("tr");

            const numberCell =
                document.createElement("td");

            numberCell.textContent =
                String(index + 1);

            const studentCell =
                document.createElement("td");

            studentCell.className = "student-name";

            const name =
                document.createElement("strong");

            name.textContent =
                `${student.lastname}, ${student.firstname}`;

            const lrn =
                document.createElement("small");

            lrn.textContent =
                student.lrn || "No LRN";

            studentCell.append(name, lrn);

            const statusCell =
                document.createElement("td");

            statusCell.appendChild(
                createStatusSelect(student)
            );

            const remarksCell =
                document.createElement("td");

            const remarks =
                document.createElement("input");

            remarks.type = "text";
            remarks.maxLength = 200;
            remarks.className =
                "form-control remarks-input";
            remarks.placeholder = "Optional";
            remarks.dataset.studentId =
                String(student.student_id);

            remarksCell.appendChild(remarks);

            row.append(
                numberCell,
                studentCell,
                statusCell,
                remarksCell
            );

            rowsContainer.appendChild(row);
        });
    }

    function toggleStudentFields() {
        const isClassDay =
            selectedDayType() === "class_day";

        document
            .querySelectorAll(
                ".offline-student-status, .remarks-input"
            )
            .forEach((field) => {
                field.disabled = !isClassDay;
            });

        rowsContainer.closest(".table-responsive")
            .hidden = !isClassDay;

        nonClassMessage.hidden = isClassDay;
    }

    async function recordsForDate(attendanceDate) {
        const records =
            await window.N1OfflineDB.getAll(
                "cached_attendance"
            );

        return records.filter((record) => (
            Number(record.class_id) === classId &&
            record.attendance_date === attendanceDate
        ));
    }

    async function loadSavedAttendance() {
        const attendanceDate = dateInput.value;

        if (!attendanceDate) {
            return;
        }

        const records = await recordsForDate(
            attendanceDate
        );

        const dayRecord = records.find(
            (record) =>
                record.record_type === "day"
        );

        const dayType =
            dayRecord?.day_type || "class_day";

        const dayTypeInput =
            document.querySelector(
                `input[name="offline_day_type"][value="${dayType}"]`
            );

        if (dayTypeInput) {
            dayTypeInput.checked = true;
        }

        noteInput.value =
            dayRecord?.note || "";

        for (const record of records) {
            if (record.record_type !== "student") {
                continue;
            }

            const status = document.querySelector(
                `.offline-student-status[data-student-id="${record.student_id}"]`
            );

            const remarks = document.querySelector(
                `.remarks-input[data-student-id="${record.student_id}"]`
            );

            if (status) {
                status.value =
                    record.status || "present";
            }

            if (remarks) {
                remarks.value =
                    record.remarks || "";
            }
        }

        toggleStudentFields();

        showMessage(
            dayRecord
                ? "Saved attendance loaded from this device."
                : ""
        );
    }

    async function clearExistingRecords(
        attendanceDate
    ) {
        const records = await recordsForDate(
            attendanceDate
        );

        for (const record of records) {
            await window.N1OfflineDB.remove(
                "cached_attendance",
                record.local_id
            );
        }
    }

    async function queueAttendance(
        attendanceDate,
        dayLocalId
    ) {
        const queue =
            await window.N1OfflineDB.getAll(
                "offline_queue"
            );

        const existing = queue.find((item) => (
            item.action_type === "attendance_sync" &&
            Number(item.target_id) === classId &&
            item.attendance_date === attendanceDate &&
            item.status !== "completed"
        ));

        const queueItem = {
            ...(existing || {}),
            action_type: "attendance_sync",
            target_table: "attendance_record",
            target_id: classId,
            class_id: classId,
            attendance_date: attendanceDate,
            day_local_id: dayLocalId,
            status: "pending",
            created_at:
                existing?.created_at ||
                new Date().toISOString(),
            updated_at: new Date().toISOString(),
            synced_at: null,
            retry_count:
                Number(existing?.retry_count || 0),
            error_message: "",
        };

        await window.N1OfflineDB.put(
            "offline_queue",
            queueItem
        );
    }

    async function saveAttendance(event) {
        event.preventDefault();

        const attendanceDate =
            dateInput.value;

        if (!attendanceDate) {
            showMessage(
                "Select an attendance date.",
                true
            );
            return;
        }

        const dayType =
            selectedDayType();

        const savedAt =
            new Date().toISOString();

        const dayLocalId =
            `day:${classId}:${attendanceDate}`;

        try {
            await clearExistingRecords(
                attendanceDate
            );

            await window.N1OfflineDB.put(
                "cached_attendance",
                {
                    local_id: dayLocalId,
                    record_type: "day",
                    class_id: classId,
                    attendance_date:
                        attendanceDate,
                    day_type: dayType,
                    note: noteInput.value
                        .trim()
                        .slice(0, 150),
                    recorded_by:
                        cachedClass.teacher_id,
                    sync_status: "pending",
                    created_at: savedAt,
                    updated_at: savedAt,
                }
            );

            if (dayType === "class_day") {
                for (const student of cachedStudents) {
                    const status =
                        document.querySelector(
                            `.offline-student-status[data-student-id="${student.student_id}"]`
                        );

                    const remarks =
                        document.querySelector(
                            `.remarks-input[data-student-id="${student.student_id}"]`
                        );

                    await window.N1OfflineDB.put(
                        "cached_attendance",
                        {
                            local_id:
                                `${classId}:${attendanceDate}:${student.student_id}`,
                            record_type: "student",
                            class_id: classId,
                            student_id:
                                student.student_id,
                            attendance_date:
                                attendanceDate,
                            status:
                                status?.value ||
                                "present",
                            remarks:
                                remarks?.value
                                    .trim()
                                    .slice(0, 200) ||
                                "",
                            sync_status: "pending",
                            created_at: savedAt,
                            updated_at: savedAt,
                        }
                    );
                }
            }

            await queueAttendance(
                attendanceDate,
                dayLocalId
            );

            showMessage(
                navigator.onLine
                    ? "Attendance saved on this device and queued for synchronization."
                    : "Attendance saved offline and queued for synchronization."
            );

            if (
                navigator.onLine &&
                window.N1AttendanceSync
            ) {
                showMessage(
                    "Attendance saved. Synchronizing..."
                );

                await window.N1AttendanceSync.syncNow();
            }
        } catch (error) {
            console.error(
                "Offline attendance save failed:",
                error
            );

            showMessage(
                error.message ||
                "Attendance could not be saved.",
                true
            );
        }
    }

    window.addEventListener(
        "n1:attendance-sync",
        (event) => {
            if (
                Number(event.detail?.classId) !==
                    classId ||
                event.detail?.attendanceDate !==
                    dateInput.value
            ) {
                return;
            }

            if (event.detail.status === "completed") {
                showMessage(
                    "Attendance synchronized successfully."
                );
            }

            if (event.detail.status === "failed") {
                showMessage(
                    event.detail.message ||
                    "Attendance synchronization failed.",
                    true
                );
            }
        }
    );

    async function initialize() {
        updateConnectionStatus();

        if (!classId) {
            showError(
                "No class was selected."
            );
            return;
        }

        if (!window.N1OfflineDB) {
            showError(
                "The offline database is unavailable."
            );
            return;
        }

        try {
            await window.N1OfflineDB.open();

            cachedClass =
                await window.N1OfflineDB.get(
                    "cached_classes",
                    classId
                );

            if (!cachedClass) {
                throw new Error(
                    "This class has not been prepared for offline attendance."
                );
            }

            const allStudents =
                await window.N1OfflineDB.getAll(
                    "cached_students"
                );

            cachedStudents = allStudents
                .filter(
                    (student) =>
                        Number(student.class_id) ===
                        classId
                )
                .sort((first, second) => (
                    first.lastname.localeCompare(
                        second.lastname
                    ) ||
                    first.firstname.localeCompare(
                        second.firstname
                    )
                ));

            className.textContent =
                cachedClass.class_name;

            classDetails.textContent = [
                cachedClass.subject,
                cachedClass.grade_level,
                cachedClass.section,
                cachedClass.school_year,
            ]
                .filter(Boolean)
                .join(" · ");

            rosterCount.textContent =
                `${cachedStudents.length} learners`;

            const backToOnlineAttendance =
                document.getElementById(
                    "backToOnlineAttendance"
                );

            if (backToOnlineAttendance) {
                backToOnlineAttendance.href =
                    `/classroom/classes/${classId}/attendance/`;
            }

            dateInput.value = localToday();

            renderStudents();

            await loadSavedAttendance();

            app.hidden = false;
        } catch (error) {
            showError(
                error.message ||
                "Offline attendance could not be opened."
            );
        }
    }

    form.addEventListener(
        "submit",
        saveAttendance
    );

    dateInput.addEventListener(
        "change",
        loadSavedAttendance
    );

    document
        .querySelectorAll(
            'input[name="offline_day_type"]'
        )
        .forEach((input) => {
            input.addEventListener(
                "change",
                toggleStudentFields
            );
        });

    window.addEventListener(
        "online",
        updateConnectionStatus
    );

    window.addEventListener(
        "offline",
        updateConnectionStatus
    );

    document.addEventListener(
        "DOMContentLoaded",
        initialize
    );
})();
