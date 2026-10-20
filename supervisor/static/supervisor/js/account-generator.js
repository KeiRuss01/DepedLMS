(function () {
    "use strict";

    const form = document.querySelector(".generated-account-form");
    if (!form) return;

    const firstName = form.querySelector("#id_firstname");
    const middleName = form.querySelector("#id_middlename");
    const lastName = form.querySelector("#id_lastname");
    const email = form.querySelector("#id_email");
    const password = form.querySelector("#id_password1");
    const currentYear = form.dataset.currentYear;

    function words(value) {
        return value
            .normalize("NFKD")
            .replace(/[\u0300-\u036f]/g, "")
            .match(/[a-zA-Z0-9]+/g) || [];
    }

    function token(value) {
        return words(value).join("").toLowerCase();
    }

    function initials(value) {
        return words(value).map((part) => part[0].toLowerCase()).join("");
    }

    function passwordName(value) {
        return words(value)
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
            .join("");
    }

    function updateAccountPreview() {
        const familyName = token(lastName.value);
        const givenInitials = initials(firstName.value);
        const middleInitial = initials(middleName.value).charAt(0);

        if (familyName && givenInitials) {
            const parts = [familyName, givenInitials];
            if (middleInitial) parts.push(middleInitial);
            email.value = `${parts.join(".")}@gmail.com`;
        } else {
            email.value = "";
        }

        password.value = familyName
            ? `${passwordName(lastName.value)}${currentYear}`
            : "";
    }

    [firstName, middleName, lastName].forEach((field) => {
        field.addEventListener("input", updateAccountPreview);
    });

    updateAccountPreview();
})();
