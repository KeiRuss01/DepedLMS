const dayTypeInputs = document.querySelectorAll('input[name="day_type"]');
const studentFields = document.getElementById("studentAttendanceFields");
const nonClassMessage = document.getElementById("nonClassMessage");

function updateAttendanceFields() {
    if (!dayTypeInputs.length || !studentFields || !nonClassMessage) return;
    const selected = document.querySelector('input[name="day_type"]:checked');
    const isClassDay = selected && selected.value === "class_day";
    studentFields.hidden = !isClassDay;
    nonClassMessage.hidden = isClassDay;
}

dayTypeInputs.forEach((input) => input.addEventListener("change", updateAttendanceFields));
updateAttendanceFields();
