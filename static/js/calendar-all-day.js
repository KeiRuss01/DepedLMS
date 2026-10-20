(function () {
    "use strict";

    document.querySelectorAll(".calendar-event-form").forEach((form) => {
        const allDay = form.querySelector("#id_all_day");
        const startInput = form.querySelector("#id_start_at");
        const endInput = form.querySelector("#id_end_at");

        if (!allDay || !startInput || !endInput) return;

        const startLabel = form.querySelector(`label[for="${startInput.id}"]`);
        const endLabel = form.querySelector(`label[for="${endInput.id}"]`);

        function datePart(value) {
            return value ? value.slice(0, 10) : "";
        }

        function restoreTimedValue(input, dateValue, defaultTime) {
            if (!dateValue) return "";
            const savedTime = (input.dataset.timedValue || "").split("T")[1];
            return `${dateValue}T${savedTime || defaultTime}`;
        }

        function updateDateMode() {
            if (allDay.checked) {
                const startDate = datePart(startInput.value);
                const endDate = datePart(endInput.value);
                if (startInput.value.includes("T")) {
                    startInput.dataset.timedValue = startInput.value.slice(0, 16);
                }
                if (endInput.value.includes("T")) {
                    endInput.dataset.timedValue = endInput.value.slice(0, 16);
                }
                startInput.type = "date";
                endInput.type = "date";
                startInput.value = startDate;
                endInput.value = endDate;
                if (startLabel) startLabel.textContent = "Start date";
                if (endLabel) endLabel.textContent = "End date";
            } else {
                const startDate = datePart(startInput.value);
                const endDate = datePart(endInput.value);
                startInput.type = "datetime-local";
                endInput.type = "datetime-local";
                startInput.value = restoreTimedValue(startInput, startDate, "08:00");
                endInput.value = restoreTimedValue(endInput, endDate, "17:00");
                if (startLabel) startLabel.textContent = "Start date and time";
                if (endLabel) endLabel.textContent = "End date and time";
            }
        }

        allDay.addEventListener("change", updateDateMode);
        updateDateMode();
    });
})();
