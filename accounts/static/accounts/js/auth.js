document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-password-toggle]').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.querySelector(button.dataset.passwordToggle);
            if (!input) return;
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            const icon = button.querySelector('i');
            if (icon) {
                icon.classList.toggle('bi-eye', !show);
                icon.classList.toggle('bi-eye-slash', show);
            }
        });
    });

    const roleInputs = document.querySelectorAll('input[name="role"]');
    const roleSections = document.querySelectorAll('[data-role-section]');
    const schoolField = document.getElementById('id_school');
    const employeeField = document.getElementById('id_employee_id');
    const studentSection = document.querySelector('[data-role-section="student"]');
    const teacherSection = document.querySelector('[data-role-section="teacher"]');

    function placeSharedFields(role) {
        if (schoolField) {
            const destination = role === 'teacher' || role === 'principal'
                ? document.querySelector(`[data-role-section="${role}"] [data-school-copy]`)
                : studentSection?.querySelector('.row > div:first-child');
            if (destination && schoolField.parentElement !== destination) destination.appendChild(schoolField);
        }
        if (employeeField) {
            const destination = role === 'principal'
                ? document.querySelector('[data-role-section="principal"] [data-employee-copy]')
                : teacherSection?.querySelector('.row > div:nth-child(2)');
            if (destination && employeeField.parentElement !== destination) destination.appendChild(employeeField);
        }
    }

    function updateRole() {
        const selected = document.querySelector('input[name="role"]:checked')?.value || 'student';
        document.querySelectorAll('[data-role-card]').forEach((card) => {
            card.classList.toggle('selected', card.dataset.roleCard === selected);
        });
        roleSections.forEach((section) => {
            section.hidden = section.dataset.roleSection !== selected;
        });
        placeSharedFields(selected);
    }

    roleInputs.forEach((input) => input.addEventListener('change', updateRole));
    if (roleInputs.length) updateRole();
});
