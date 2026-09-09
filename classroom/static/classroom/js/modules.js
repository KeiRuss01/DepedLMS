/* Layout preview only: no fetch(), database writes, or browser storage. */
(() => {
    const app = document.getElementById('moduleApp');
    if (!app) return;
    const find = (id) => document.getElementById(id);
    const teacher = app.dataset.role === 'teacher';
    let pdfUrl = null;
    let mode = 'structured';
    let items = [];
    let draft = null;
    let selectedTerm = 'all';
    let nextItemId = 1;
    const answers = new Map();

    function notice(message) {
        find('mmNotice').textContent = message;
        find('mmNotice').hidden = false;
        find('mmNotice').scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function showScreen(name) {
        const target = app.querySelector(`[data-screen="${name}"]`);
        if (!target) return;
        app.querySelectorAll('[data-screen]').forEach(screen => { screen.hidden = screen !== target; });
        find('mmNotice').hidden = true;
        if (name === 'workspace') renderAnswers();
        const heading = target.querySelector('h2');
        if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
        app.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function selectPdf(input) {
        const file = input.files[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf')) {
            input.value = '';
            notice('Please choose a PDF file.');
            return;
        }
        if (pdfUrl) URL.revokeObjectURL(pdfUrl);
        pdfUrl = URL.createObjectURL(file);
        find('mmPdfFrame').src = pdfUrl;
        find('mmPdfFrame').hidden = false;
        find('mmPdfEmpty').hidden = true;
        find('mmOpenPdf').href = pdfUrl;
        find('mmOpenPdf').hidden = false;
        if (find('mmPdfName')) find('mmPdfName').textContent = `${file.name} — local preview only`;
    }

    function makeItems(count, type) {
        items = Array.from({ length: count }, (_, index) => ({ id: nextItemId++, label: `Item ${index + 1}`, type }));
        answers.clear();
        if (teacher) renderBuilder();
    }

    function renderBuilder() {
        const container = find('mmBuilderItems');
        container.replaceChildren();
        items.forEach((item, index) => {
            const row = document.createElement('div');
            row.className = 'mm-builder-item';
            const number = document.createElement('span');
            number.textContent = `#${index + 1}`;
            const label = document.createElement('input');
            label.className = 'form-control'; label.value = item.label;
            label.maxLength = 250;
            label.setAttribute('aria-label', `Label or page reference for item ${index + 1}`);
            label.addEventListener('input', () => { item.label = label.value; });
            const select = document.createElement('select');
            select.className = 'form-select';
            select.setAttribute('aria-label', `Answer type for item ${index + 1}`);
            [['short', 'Short answer'], ['choice', 'Multiple choice'], ['essay', 'Long answer']].forEach(([value, text]) => select.add(new Option(text, value)));
            select.value = item.type;
            select.addEventListener('change', () => { item.type = select.value; answers.delete(item.id); });
            const remove = document.createElement('button');
            remove.type = 'button'; remove.className = 'btn btn-light border'; remove.textContent = '×';
            remove.setAttribute('aria-label', `Remove item ${index + 1}`);
            remove.addEventListener('click', () => { items = items.filter(other => other.id !== item.id); answers.delete(item.id); renderBuilder(); });
            row.append(number, label, select, remove); container.append(row);
        });
    }

    function updateProgress() {
        let total = 0;
        let completed = 0;
        if (mode === 'structured') {
            total = items.length;
            completed = items.filter(item => (answers.get(item.id) || '').trim()).length;
        } else {
            total = 1;
            completed = mode === 'written' ? Number(Boolean(find('mmResponse').value.trim())) : Number(Boolean(find('mmAnswerFile').files.length));
        }
        find('mmAnswerProgress').textContent = `${completed} of ${total} answered`;
        return { total, completed };
    }

    function renderAnswers() {
        const container = find('mmStructuredAnswers');
        container.hidden = mode !== 'structured';
        find('mmWrittenAnswer').hidden = mode !== 'written';
        find('mmFileAnswer').hidden = mode !== 'file';
        container.replaceChildren();
        items.forEach((item, index) => {
            const fieldset = document.createElement('fieldset');
            fieldset.className = 'mm-answer-item';
            const legend = document.createElement('legend');
            legend.textContent = item.label.trim() || `Item ${index + 1}`;
            fieldset.append(legend);
            if (item.type === 'choice') {
                ['A', 'B', 'C', 'D'].forEach(letter => {
                    const label = document.createElement('label'); label.className = 'mm-choice';
                    const input = document.createElement('input');
                    input.type = 'radio'; input.name = `answer_${item.id}`; input.value = letter;
                    input.checked = answers.get(item.id) === letter;
                    input.addEventListener('change', () => { answers.set(item.id, letter); updateProgress(); });
                    label.append(input, document.createTextNode(letter)); fieldset.append(label);
                });
            } else {
                const input = document.createElement(item.type === 'essay' ? 'textarea' : 'input');
                if (item.type === 'short') input.type = 'text';
                input.className = 'form-control'; input.value = answers.get(item.id) || '';
                input.placeholder = 'Your answer'; input.setAttribute('aria-label', legend.textContent);
                input.addEventListener('input', () => { answers.set(item.id, input.value); updateProgress(); });
                fieldset.append(input);
            }
            container.append(fieldset);
        });
        if (!items.length && mode === 'structured') container.textContent = 'No answer fields added yet. Return to module setup to create them.';
        find('mmSubmissionReview').hidden = true;
        updateProgress();
    }

    function readSetup() {
        const form = find('mmSetupForm');
        if (!form.reportValidity()) return false;
        if (mode === 'structured' && !items.length) { notice('Create at least one answer field or choose another response method.'); return false; }
        draft = { title: find('mmTitle').value.trim(), term: find('mmTerm').value, score: find('mmMaxScore').value };
        if (!draft.title) { notice('Enter a module title.'); return false; }
        find('mmWorkspaceTitle').textContent = draft.title;
        find('mmWorkspaceTerm').textContent = `Term ${draft.term} · ${find('mmYear').value}`;
        find('mmWorkspaceInstructions').textContent = find('mmInstructions').value || 'Read the PDF and complete the answer sheet.';
        find('mmGrade').max = draft.score;
        find('mmGradeMax').textContent = `/ ${draft.score}`;
        find('mmCardTitle').textContent = draft.title;
        find('mmCardTerm').textContent = `Term ${draft.term}`;
        find('mmCardMeta').textContent = `${draft.score} points · ${mode === 'structured' ? `${items.length} answer fields` : mode === 'written' ? 'Written response' : 'Answer file'}`;
        filterLibrary();
        return true;
    }

    function filterLibrary() {
        const search = find('mmSearch').value.trim().toLowerCase();
        const visible = Boolean(draft && (selectedTerm === 'all' || selectedTerm === draft.term) && draft.title.toLowerCase().includes(search));
        find('mmDraftCard').hidden = !visible;
        find('mmLibraryEmpty').hidden = visible;
        find('mmLibraryEmpty').querySelector('h3').textContent = draft ? 'No matching modules' : 'No modules yet';
    }

    app.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => showScreen(button.dataset.open)));
    app.querySelectorAll('[data-preview-action]').forEach(button => button.addEventListener('click', () => notice(button.dataset.previewAction)));
    app.querySelectorAll('[data-term]').forEach(button => button.addEventListener('click', () => {
        selectedTerm = button.dataset.term;
        app.querySelectorAll('[data-term]').forEach(tab => { tab.classList.toggle('is-active', tab === button); tab.setAttribute('aria-pressed', String(tab === button)); });
        filterLibrary();
    }));
    find('mmSearch').addEventListener('input', filterLibrary);
    app.querySelectorAll('[data-pane]').forEach(button => button.addEventListener('click', () => {
        app.querySelector('.mm-workspace').dataset.mobilePane = button.dataset.pane;
        app.querySelectorAll('[data-pane]').forEach(tab => { tab.classList.toggle('is-active', tab === button); tab.setAttribute('aria-pressed', String(tab === button)); });
    }));

    if (teacher) {
        find('mmPdf').addEventListener('change', event => selectPdf(event.target));
        app.querySelectorAll('[name="answer_mode"]').forEach(input => input.addEventListener('change', () => {
            mode = input.value;
            find('mmBuilder').hidden = mode !== 'structured';
            find('mmItemCount').disabled = mode !== 'structured';
        }));
        find('mmBuildItems').addEventListener('click', () => {
            const count = find('mmItemCount');
            if (!count.reportValidity()) return;
            if (!count.value) { notice('Enter the number of answer fields to create.'); return; }
            if (items.length && !window.confirm('Replace the current answer fields? Any preview answers for these fields will be cleared.')) return;
            makeItems(Number(count.value), find('mmItemType').value);
        });
        find('mmSetupForm').addEventListener('submit', event => { event.preventDefault(); if (readSetup()) showScreen('workspace'); });
        find('mmSavePreview').addEventListener('click', () => { if (readSetup()) { showScreen('library'); notice('Draft kept in this page only. Refreshing or leaving the page will clear it.'); } });
        find('mmGradeForm').addEventListener('submit', event => { event.preventDefault(); notice('Score and feedback are preview values only. Nothing was returned or saved.'); });
    } else {
        find('mmStudentPdf').addEventListener('change', event => selectPdf(event.target));
        find('mmPreviewMode').addEventListener('change', event => { mode = event.target.value; renderAnswers(); });
    }
    find('mmResponse').addEventListener('input', updateProgress);
    find('mmAnswerFile').addEventListener('change', event => { find('mmAnswerFileName').textContent = event.target.files[0]?.name || 'No file selected.'; updateProgress(); });
    find('mmAnswerForm').addEventListener('submit', event => {
        event.preventDefault();
        const progress = updateProgress();
        find('mmReviewSummary').textContent = `${progress.completed} of ${progress.total} responses completed. ${progress.completed < progress.total ? 'Some responses are still blank.' : 'Check your answers before submitting.'}`;
        find('mmSubmissionReview').hidden = false;
        find('mmSubmissionReview').focus();
        find('mmSubmissionReview').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    find('mmReturnAnswers').addEventListener('click', () => { find('mmSubmissionReview').hidden = true; app.querySelector('[data-pane="answers"]').click(); find('mmAnswerForm').scrollIntoView({ behavior: 'smooth' }); });
    window.addEventListener('pagehide', () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); });
    makeItems(5, 'short');
})();
