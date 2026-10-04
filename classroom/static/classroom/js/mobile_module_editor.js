const editor = document.getElementById("mobileModuleEditor");

if (editor) {
    startMobileModuleEditor(editor);
}

async function startMobileModuleEditor(editor) {
    const editable = editor.dataset.editable === "true";
    const csrfToken = editor.dataset.csrfToken;

    const pdfCanvas = document.getElementById("mobilePdfCanvas");
    const annotationCanvas = document.getElementById(
        "mobileAnnotationCanvas"
    );

    const pdfContext = pdfCanvas.getContext("2d");
    const annotationContext = annotationCanvas.getContext("2d");

    const stage = document.getElementById("mobilePdfStage");
    const pageLabel = document.getElementById("mobilePdfPageLabel");
    const previousButton = document.getElementById("mobilePdfPrevious");
    const nextButton = document.getElementById("mobilePdfNext");
    const errorBox = document.getElementById("mobilePdfError");
    const draftStatus = document.getElementById("mobileDraftStatus");
    const undoButton = document.getElementById("mobileUndo");
    const textSizeSelect = document.getElementById("mobileTextSize");

    let pdfDocument = null;
    let currentPage = 1;
    let annotations = [];
    let extraPages = [];
    let activeTool = "type";
    let activePointer = null;
    let previewAnnotation = null;
    let rendering = false;
    let saveTimer = null;
    let saving = false;
    let saveAgain = false;
    let undoHistory = [];
    let selectedAnnotationId = null;
    let activeTextSize = 0.026;

    function createId() {
        if (window.crypto && window.crypto.randomUUID) {
            return window.crypto.randomUUID();
        }

        return `annotation-${Date.now()}-${Math.random()
            .toString(16)
            .slice(2)}`;
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
    }

    function clearError() {
        errorBox.hidden = true;
        errorBox.textContent = "";
    }

    function setDraftStatus(message, state = "normal") {
        draftStatus.classList.remove(
            "is-saving",
            "is-saved",
            "is-error"
        );

        if (state === "saving") {
            draftStatus.classList.add("is-saving");
            draftStatus.innerHTML =
                '<i class="bi bi-arrow-repeat"></i> Saving...';
            return;
        }

        if (state === "saved") {
            draftStatus.classList.add("is-saved");
            draftStatus.innerHTML =
                '<i class="bi bi-cloud-check-fill"></i> Saved';
            return;
        }

        if (state === "error") {
            draftStatus.classList.add("is-error");
            draftStatus.innerHTML =
                '<i class="bi bi-exclamation-circle-fill"></i> Save failed';
            return;
        }

        draftStatus.textContent = message;
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                "X-CSRFToken": csrfToken,
                ...(options.headers || {}),
            },
        });

        let data = {};

        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }

        if (!response.ok) {
            throw new Error(
                data.error || "The request could not be completed."
            );
        }

        return data;
    }

    async function loadDraft() {
        if (!editable) {
            return;
        }

        try {
            const data = await requestJson(
                editor.dataset.draftStateUrl
            );

            annotations = Array.isArray(data.annotations)
                ? data.annotations
                : [];

            extraPages = Array.isArray(data.extra_pages)
                ? data.extra_pages
                : [];

            currentPage = Number(data.current_page) || 1;

            renderExtraPages();
            updateUndoButton();

            if (!data.editable) {
                disableEditor(
                    "This Module can no longer be changed."
                );
            }

            if (data.draft_saved_at) {
                setDraftStatus("Saved", "saved");
            } else {
                setDraftStatus("Not saved yet");
            }
        } catch (error) {
            setDraftStatus("Draft unavailable", "error");
            showError(error.message);
        }
    }

    function scheduleAnnotationSave() {
        if (!editable) {
            return;
        }

        window.clearTimeout(saveTimer);
        setDraftStatus("Saving", "saving");

        saveTimer = window.setTimeout(() => {
            saveAnnotationDraft();
        }, 800);
    }

    async function saveAnnotationDraft() {
        if (!editable) {
            return true;
        }

        if (saving) {
            saveAgain = true;
            return false;
        }

        saving = true;
        saveAgain = false;

        try {
            await requestJson(editor.dataset.annotationSaveUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    current_page: currentPage,
                    annotations,
                }),
            });

            setDraftStatus("Saved", "saved");
            clearError();
            return true;
        } catch (error) {
            setDraftStatus("Save failed", "error");
            showError(error.message);
            return false;
        } finally {
            saving = false;

            if (saveAgain) {
                saveAnnotationDraft();
            }
        }
    }

    function updateNavigation() {
        previousButton.disabled =
            !pdfDocument || currentPage <= 1;

        nextButton.disabled =
            !pdfDocument ||
            currentPage >= pdfDocument.numPages;
    }

    async function changePage(newPage) {
        if (!pdfDocument) {
            return;
        }

        currentPage = Math.min(
            Math.max(newPage, 1),
            pdfDocument.numPages
        );

        await renderCurrentPage();

        if (editable) {
            scheduleAnnotationSave();
        }
    }

    async function renderCurrentPage() {
        if (!pdfDocument || rendering) {
            return;
        }

        rendering = true;

        try {
            const page = await pdfDocument.getPage(currentPage);
            const originalViewport = page.getViewport({ scale: 1 });

            const availableWidth = Math.max(
                280,
                stage.clientWidth - 24
            );

            const scale =
                availableWidth / originalViewport.width;

            const viewport = page.getViewport({ scale });

            const pixelRatio = Math.min(
                window.devicePixelRatio || 1,
                2
            );

            pdfCanvas.width = Math.floor(
                viewport.width * pixelRatio
            );

            pdfCanvas.height = Math.floor(
                viewport.height * pixelRatio
            );

            pdfCanvas.style.width = `${viewport.width}px`;
            pdfCanvas.style.height = `${viewport.height}px`;

            annotationCanvas.width = pdfCanvas.width;
            annotationCanvas.height = pdfCanvas.height;

            annotationCanvas.style.width =
                `${viewport.width}px`;

            annotationCanvas.style.height =
                `${viewport.height}px`;

            await page.render({
                canvasContext: pdfContext,
                viewport,
                transform: [
                    pixelRatio,
                    0,
                    0,
                    pixelRatio,
                    0,
                    0,
                ],
            }).promise;

            pageLabel.textContent =
                `Page ${currentPage} of ${pdfDocument.numPages}`;

            drawAnnotations();
            updateNavigation();
            clearError();
        } catch (error) {
            showError(
                "This Module page could not be displayed."
            );
        } finally {
            rendering = false;
        }
    }

    function normalizedPointer(event, canvas = annotationCanvas) {
        const rectangle = canvas.getBoundingClientRect();

        return {
            x: Math.min(
                Math.max(
                    (event.clientX - rectangle.left) /
                    rectangle.width,
                    0
                ),
                1
            ),
            y: Math.min(
                Math.max(
                    (event.clientY - rectangle.top) /
                    rectangle.height,
                    0
                ),
                1
            ),
        };
    }

    function drawAnnotations() {
        annotationContext.clearRect(
            0,
            0,
            annotationCanvas.width,
            annotationCanvas.height
        );

        const pageAnnotations = annotations.filter(
            (annotation) =>
                Number(annotation.page) === currentPage
        );

        pageAnnotations.forEach(drawOneAnnotation);

        const selectedAnnotation = annotations.find(
            (annotation) =>
                annotation.id === selectedAnnotationId &&
                Number(annotation.page) === currentPage
        );

        if (selectedAnnotation) {
            drawSelectionBox(selectedAnnotation);
        }

        if (previewAnnotation) {
            drawOneAnnotation(previewAnnotation);
        }
    }

    function drawOneAnnotation(annotation) {
        const width = annotationCanvas.width;
        const height = annotationCanvas.height;

        const x = Number(annotation.x || 0) * width;
        const y = Number(annotation.y || 0) * height;
        const annotationWidth =
            Number(annotation.width || 0) * width;
        const annotationHeight =
            Number(annotation.height || 0) * height;

        annotationContext.save();
        annotationContext.lineCap = "round";
        annotationContext.lineJoin = "round";

        if (annotation.tool === "type") {
            const fontSize = Math.max(
                15,
                Number(annotation.size || 0.026) * height
            );

            annotationContext.fillStyle =
                annotation.color || "#0b57d0";

            annotationContext.font =
                `${fontSize}px Arial, sans-serif`;

            annotationContext.textBaseline = "top";

            const lines = String(annotation.text || "").split("\n");

            lines.forEach((line, index) => {
                annotationContext.fillText(
                    line,
                    x,
                    y + index * fontSize * 1.2
                );
            });
        }

        if (annotation.tool === "draw") {
            const points = annotation.points || [];

            if (points.length > 0) {
                annotationContext.strokeStyle =
                    annotation.color || "#0b57d0";

                annotationContext.lineWidth = Math.max(
                    2,
                    Number(annotation.size || 0.005) * width
                );

                annotationContext.beginPath();

                points.forEach((point, index) => {
                    const pointX = point.x * width;
                    const pointY = point.y * height;

                    if (index === 0) {
                        annotationContext.moveTo(pointX, pointY);
                    } else {
                        annotationContext.lineTo(pointX, pointY);
                    }
                });

                annotationContext.stroke();
            }
        }

        if (annotation.tool === "check") {
            const size = Math.max(
                20,
                Number(annotation.size || 0.04) * height
            );

            annotationContext.strokeStyle =
                annotation.color || "#16803a";

            annotationContext.lineWidth = Math.max(
                3,
                size * 0.13
            );

            annotationContext.beginPath();
            annotationContext.moveTo(x, y + size * 0.45);
            annotationContext.lineTo(
                x + size * 0.32,
                y + size * 0.75
            );
            annotationContext.lineTo(
                x + size,
                y
            );
            annotationContext.stroke();
        }

        if (annotation.tool === "circle") {
            annotationContext.strokeStyle =
                annotation.color || "#dc3545";

            annotationContext.lineWidth = Math.max(
                2,
                width * 0.004
            );

            annotationContext.beginPath();
            annotationContext.ellipse(
                x + annotationWidth / 2,
                y + annotationHeight / 2,
                Math.abs(annotationWidth / 2),
                Math.abs(annotationHeight / 2),
                0,
                0,
                Math.PI * 2
            );
            annotationContext.stroke();
        }

        if (annotation.tool === "highlight") {
            annotationContext.globalAlpha =
                Number(annotation.opacity || 0.35);

            annotationContext.fillStyle =
                annotation.color || "#ffe066";

            annotationContext.fillRect(
                x,
                y,
                annotationWidth,
                annotationHeight
            );
        }

        annotationContext.restore();
    }

    function annotationBounds(annotation) {
        if (annotation.tool === "draw") {
            const points = annotation.points || [];
            if (!points.length) {
                return null;
            }

            const xValues = points.map((point) => point.x);
            const yValues = points.map((point) => point.y);

            return {
                x: Math.min(...xValues),
                y: Math.min(...yValues),
                width: Math.max(...xValues) - Math.min(...xValues),
                height: Math.max(...yValues) - Math.min(...yValues),
            };
        }

        return {
            x: Number(annotation.x || 0),
            y: Number(annotation.y || 0),
            width: Math.max(Number(annotation.width || 0), 0.05),
            height: Math.max(Number(annotation.height || 0), 0.04),
        };
    }

    function drawSelectionBox(annotation) {
        const bounds = annotationBounds(annotation);
        if (!bounds) {
            return;
        }

        annotationContext.save();
        annotationContext.strokeStyle = "#0d6efd";
        annotationContext.lineWidth = 2;
        annotationContext.setLineDash([8, 6]);
        annotationContext.strokeRect(
            bounds.x * annotationCanvas.width - 5,
            bounds.y * annotationCanvas.height - 5,
            bounds.width * annotationCanvas.width + 10,
            bounds.height * annotationCanvas.height + 10
        );
        annotationContext.restore();
    }

    function saveUndoSnapshot() {
        undoHistory.push(
            JSON.parse(JSON.stringify(annotations))
        );

        if (undoHistory.length > 30) {
            undoHistory.shift();
        }

        updateUndoButton();
    }

    function updateUndoButton() {
        if (undoButton) {
            undoButton.disabled = undoHistory.length === 0;
        }
    }

    function addAnnotation(annotation) {
        saveUndoSnapshot();
        annotations.push(annotation);
        selectedAnnotationId = annotation.id;
        previewAnnotation = null;
        drawAnnotations();
        scheduleAnnotationSave();
    }

    function annotationContainsPoint(annotation, point) {
        const padding = 0.025;

        if (annotation.tool === "draw") {
            return (annotation.points || []).some((drawPoint) => {
                return (
                    Math.abs(drawPoint.x - point.x) <= padding &&
                    Math.abs(drawPoint.y - point.y) <= padding
                );
            });
        }

        const x = Number(annotation.x || 0);
        const y = Number(annotation.y || 0);
        const width = Math.max(
            Number(annotation.width || 0),
            0.05
        );
        const height = Math.max(
            Number(annotation.height || 0),
            0.04
        );

        return (
            point.x >= x - padding &&
            point.x <= x + width + padding &&
            point.y >= y - padding &&
            point.y <= y + height + padding
        );
    }

    function findAnnotationAtPoint(point) {
        for (let index = annotations.length - 1; index >= 0; index -= 1) {
            const annotation = annotations[index];
            if (
                Number(annotation.page) === currentPage &&
                annotationContainsPoint(annotation, point)
            ) {
                return annotation;
            }
        }
        return null;
    }

    function eraseAnnotation(point) {
        for (let index = annotations.length - 1; index >= 0; index -= 1) {
            const annotation = annotations[index];

            if (
                Number(annotation.page) === currentPage &&
                annotationContainsPoint(annotation, point)
            ) {
                saveUndoSnapshot();
                annotations.splice(index, 1);
                drawAnnotations();
                scheduleAnnotationSave();
                return;
            }
        }
    }

    function handlePointerDown(event) {
        if (!editable) {
            return;
        }

        event.preventDefault();
        annotationCanvas.setPointerCapture(event.pointerId);

        const point = normalizedPointer(event);

        if (activeTool === "type") {
            const answer = window.prompt(
                "Enter your answer:"
            );

            if (answer && answer.trim()) {
                addAnnotation({
                    id: createId(),
                    page: currentPage,
                    tool: "type",
                    x: point.x,
                    y: point.y,
                    width: 0.3,
                    height: 0.05,
                    size: activeTextSize,
                    color: "#0b57d0",
                    text: answer.trim(),
                });
            }

            return;
        }

        if (activeTool === "check") {
            addAnnotation({
                id: createId(),
                page: currentPage,
                tool: "check",
                x: point.x,
                y: point.y,
                width: 0.06,
                height: 0.06,
                size: 0.04,
                color: "#16803a",
            });

            return;
        }

        if (activeTool === "erase") {
            eraseAnnotation(point);
            return;
        }

        if (activeTool === "move") {
            const annotation = findAnnotationAtPoint(point);
            selectedAnnotationId = annotation?.id || null;

            if (!annotation) {
                drawAnnotations();
                return;
            }

            if (annotation.tool === "type" && textSizeSelect) {
                textSizeSelect.value = String(
                    Number(annotation.size || 0.026)
                );
            }

            saveUndoSnapshot();
            activePointer = {
                pointerId: event.pointerId,
                start: point,
                mode: "move",
                annotationId: annotation.id,
                original: JSON.parse(JSON.stringify(annotation)),
            };
            drawAnnotations();
            return;
        }

        activePointer = {
            pointerId: event.pointerId,
            start: point,
        };

        if (activeTool === "draw") {
            previewAnnotation = {
                id: createId(),
                page: currentPage,
                tool: "draw",
                color: "#0b57d0",
                size: 0.005,
                points: [point],
            };
        }

        if (
            activeTool === "circle" ||
            activeTool === "highlight"
        ) {
            previewAnnotation = {
                id: createId(),
                page: currentPage,
                tool: activeTool,
                x: point.x,
                y: point.y,
                width: 0,
                height: 0,
                color:
                    activeTool === "circle"
                        ? "#dc3545"
                        : "#ffe066",
                opacity:
                    activeTool === "highlight"
                        ? 0.35
                        : 1,
            };
        }

        drawAnnotations();
    }

    function handlePointerMove(event) {
        if (
            !activePointer ||
            activePointer.pointerId !== event.pointerId
        ) {
            return;
        }

        event.preventDefault();

        const point = normalizedPointer(event);

        if (activePointer.mode === "move") {
            const annotation = annotations.find(
                (item) => item.id === activePointer.annotationId
            );
            if (!annotation) {
                return;
            }

            const deltaX = point.x - activePointer.start.x;
            const deltaY = point.y - activePointer.start.y;
            const original = activePointer.original;

            if (annotation.tool === "draw") {
                annotation.points = (original.points || []).map(
                    (drawPoint) => ({
                        x: Math.min(Math.max(drawPoint.x + deltaX, 0), 1),
                        y: Math.min(Math.max(drawPoint.y + deltaY, 0), 1),
                    })
                );
            } else {
                annotation.x = Math.min(
                    Math.max(Number(original.x || 0) + deltaX, 0),
                    1
                );
                annotation.y = Math.min(
                    Math.max(Number(original.y || 0) + deltaY, 0),
                    1
                );
            }

            drawAnnotations();
            return;
        }

        if (!previewAnnotation) {
            return;
        }

        if (previewAnnotation.tool === "draw") {
            previewAnnotation.points.push(point);
        } else {
            previewAnnotation.x = Math.min(
                activePointer.start.x,
                point.x
            );

            previewAnnotation.y = Math.min(
                activePointer.start.y,
                point.y
            );

            previewAnnotation.width = Math.abs(
                point.x - activePointer.start.x
            );

            previewAnnotation.height = Math.abs(
                point.y - activePointer.start.y
            );
        }

        drawAnnotations();
    }

    function handlePointerUp(event) {
        if (
            !activePointer ||
            activePointer.pointerId !== event.pointerId
        ) {
            return;
        }

        event.preventDefault();

        if (activePointer.mode === "move") {
            activePointer = null;
            scheduleAnnotationSave();
            return;
        }

        const completedAnnotation = previewAnnotation;

        activePointer = null;
        previewAnnotation = null;

        if (!completedAnnotation) {
            return;
        }

        if (
            completedAnnotation.tool === "draw" &&
            completedAnnotation.points.length < 2
        ) {
            drawAnnotations();
            return;
        }

        if (
            ["circle", "highlight"].includes(
                completedAnnotation.tool
            ) &&
            (
                completedAnnotation.width < 0.01 ||
                completedAnnotation.height < 0.01
            )
        ) {
            drawAnnotations();
            return;
        }

        addAnnotation(completedAnnotation);
    }

    function initializeToolButtons() {
        const buttons = document.querySelectorAll(
            "[data-mobile-tool]"
        );

        const instruction = document.querySelector(
            "#mobileToolInstruction span"
        );

        const instructions = {
            type: "Tap the answer space where your text should appear.",
            draw: "Drag your finger over the Module to draw.",
            check: "Tap the location where you want a check mark.",
            circle: "Drag around the answer you want to mark.",
            highlight: "Drag across the text you want to highlight.",
            move: "Drag an answer or mark to move it.",
            erase: "Tap an answer or mark that you want to remove.",
        };

        buttons.forEach((button) => {
            button.addEventListener("click", () => {
                activeTool = button.dataset.mobileTool;

                buttons.forEach((otherButton) => {
                    const selected = otherButton === button;

                    otherButton.classList.toggle(
                        "is-selected",
                        selected
                    );

                    otherButton.setAttribute(
                        "aria-pressed",
                        String(selected)
                    );
                });

                instruction.textContent =
                    instructions[activeTool];
            });
        });

        undoButton?.addEventListener("click", () => {
            const previousAnnotations = undoHistory.pop();

            if (!previousAnnotations) {
                return;
            }

            annotations = previousAnnotations;
            drawAnnotations();
            updateUndoButton();
            scheduleAnnotationSave();
        });

        textSizeSelect?.addEventListener("change", () => {
            activeTextSize = Number(textSizeSelect.value) || 0.026;
            const selected = annotations.find(
                (annotation) => annotation.id === selectedAnnotationId
            );

            if (!selected || selected.tool !== "type") {
                return;
            }

            saveUndoSnapshot();
            selected.size = activeTextSize;
            drawAnnotations();
            scheduleAnnotationSave();
        });
    }

    function disableEditor(message) {
        document
            .querySelectorAll(
                "[data-mobile-tool], " +
                "#openAnswerPageDialog, " +
                "#mobileOutputUpload, " +
                "#mobileTextSize, " +
                "#mobileUndo"
            )
            .forEach((element) => {
                element.disabled = true;
            });

        setDraftStatus(message, "error");
    }

    /*
     * Extra answer pages
     */

    const extraPageList = document.getElementById(
        "mobileExtraPageList"
    );

    const answerPageDialog = document.getElementById(
        "answerPageDialog"
    );

    const editorDialog = document.getElementById(
        "extraPageEditorDialog"
    );

    const editorDialogTitle = document.getElementById(
        "extraPageEditorTitle"
    );

    const essayEditor = document.getElementById(
        "extraPageEssayEditor"
    );

    const drawingEditor = document.getElementById(
        "extraPageDrawingEditor"
    );

    const drawingCanvas = document.getElementById(
        "extraPageDrawingCanvas"
    );

    const drawingContext = drawingCanvas?.getContext("2d");

    let activeExtraPage = null;
    let extraPageSaveTimer = null;
    let drawingStroke = null;

    async function createExtraPage(pageType, file = null) {
        const formData = new FormData();

        formData.append("page_type", pageType);
        formData.append("related_pdf_page", currentPage);

        if (file) {
            formData.append("file", file);
            formData.append("title", file.name);
        }

        setDraftStatus("Saving", "saving");

        try {
            const data = await requestJson(
                editor.dataset.extraPageCreateUrl,
                {
                    method: "POST",
                    body: formData,
                }
            );

            extraPages.push(data.page);
            renderExtraPages();
            setDraftStatus("Saved", "saved");

            if (pageType !== "upload") {
                openExtraPageEditor(data.page.id);
            }
        } catch (error) {
            setDraftStatus("Save failed", "error");
            showError(error.message);
        }
    }

    async function updateExtraPage(page, changes) {
        setDraftStatus("Saving", "saving");

        try {
            const data = await requestJson(
                page.update_url,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(changes),
                }
            );

            const index = extraPages.findIndex(
                (item) => item.id === page.id
            );

            if (index !== -1) {
                extraPages[index] = data.page;
                activeExtraPage = data.page;
            }

            renderExtraPages();
            setDraftStatus("Saved", "saved");
            clearError();
        } catch (error) {
            setDraftStatus("Save failed", "error");
            showError(error.message);
        }
    }

    function scheduleExtraPageSave() {
        if (!activeExtraPage) {
            return;
        }

        window.clearTimeout(extraPageSaveTimer);
        setDraftStatus("Saving", "saving");

        extraPageSaveTimer = window.setTimeout(() => {
            if (activeExtraPage.page_type === "essay") {
                updateExtraPage(activeExtraPage, {
                    essay_text: essayEditor.value,
                });
            }

            if (activeExtraPage.page_type === "drawing") {
                updateExtraPage(activeExtraPage, {
                    drawing_data:
                        activeExtraPage.drawing_data || [],
                });
            }
        }, 800);
    }

    async function deleteExtraPage(page) {
        const confirmed = window.confirm(
            `Remove "${page.title}"?`
        );

        if (!confirmed) {
            return;
        }

        try {
            await requestJson(page.delete_url, {
                method: "POST",
            });

            extraPages = extraPages.filter(
                (item) => item.id !== page.id
            );

            renderExtraPages();
            setDraftStatus("Saved", "saved");
        } catch (error) {
            setDraftStatus("Delete failed", "error");
            showError(error.message);
        }
    }

    function pageIcon(pageType) {
        if (pageType === "essay") {
            return "bi-file-text";
        }

        if (pageType === "drawing") {
            return "bi-brush";
        }

        return "bi-file-earmark-arrow-up";
    }

    function renderExtraPages() {
        if (!extraPageList) {
            return;
        }

        extraPageList.innerHTML = "";

        extraPages.forEach((page) => {
            const row = document.createElement("article");
            row.className = "mobile-extra-page";

            const information = document.createElement("div");
            information.className = "mobile-extra-page-info";

            const icon = document.createElement("i");
            icon.className = `bi ${pageIcon(page.page_type)}`;

            const text = document.createElement("div");

            const title = document.createElement("strong");
            title.textContent = page.title;

            const description = document.createElement("small");
            description.textContent =
                page.original_name ||
                page.page_type_label ||
                "Answer page";

            text.append(title, description);
            information.append(icon, text);

            const actions = document.createElement("div");
            actions.className = "mobile-extra-page-actions";

            if (page.page_type === "upload" && page.file_url) {
                const openLink = document.createElement("a");
                openLink.href = page.file_url;
                openLink.target = "_blank";
                openLink.className =
                    "btn btn-sm btn-outline-primary";
                openLink.innerHTML =
                    '<i class="bi bi-eye"></i>';
                openLink.setAttribute(
                    "aria-label",
                    `Open ${page.title}`
                );

                actions.append(openLink);
            } else {
                const editButton = document.createElement("button");
                editButton.type = "button";
                editButton.className =
                    "btn btn-sm btn-outline-primary";
                editButton.innerHTML =
                    '<i class="bi bi-pencil"></i>';
                editButton.setAttribute(
                    "aria-label",
                    `Edit ${page.title}`
                );

                editButton.addEventListener("click", () => {
                    openExtraPageEditor(page.id);
                });

                actions.append(editButton);
            }

            const removeButton =
                document.createElement("button");

            removeButton.type = "button";
            removeButton.className =
                "btn btn-sm btn-outline-danger";

            removeButton.innerHTML =
                '<i class="bi bi-trash"></i>';

            removeButton.setAttribute(
                "aria-label",
                `Remove ${page.title}`
            );

            removeButton.addEventListener("click", () => {
                deleteExtraPage(page);
            });

            actions.append(removeButton);
            row.append(information, actions);
            extraPageList.append(row);
        });
    }

    function openExtraPageEditor(pageId) {
        activeExtraPage = extraPages.find(
            (page) => page.id === pageId
        );

        if (!activeExtraPage || !editorDialog) {
            return;
        }

        editorDialogTitle.textContent =
            activeExtraPage.title;

        essayEditor.hidden =
            activeExtraPage.page_type !== "essay";

        drawingEditor.hidden =
            activeExtraPage.page_type !== "drawing";

        if (activeExtraPage.page_type === "essay") {
            essayEditor.value =
                activeExtraPage.essay_text || "";
        }

        if (activeExtraPage.page_type === "drawing") {
            window.setTimeout(() => {
                resizeDrawingCanvas();
                renderExtraDrawing();
            }, 0);
        }

        editorDialog.showModal();
    }

    function resizeDrawingCanvas() {
        if (!drawingCanvas) {
            return;
        }

        const width = drawingCanvas.clientWidth || 320;
        const height = Math.max(430, width * 1.25);
        const ratio = Math.min(
            window.devicePixelRatio || 1,
            2
        );

        drawingCanvas.width = width * ratio;
        drawingCanvas.height = height * ratio;
        drawingCanvas.style.height = `${height}px`;
    }

    function renderExtraDrawing() {
        if (!drawingContext || !activeExtraPage) {
            return;
        }

        drawingContext.clearRect(
            0,
            0,
            drawingCanvas.width,
            drawingCanvas.height
        );

        drawingContext.fillStyle = "#ffffff";
        drawingContext.fillRect(
            0,
            0,
            drawingCanvas.width,
            drawingCanvas.height
        );

        drawingContext.lineCap = "round";
        drawingContext.lineJoin = "round";

        (activeExtraPage.drawing_data || []).forEach(
            (stroke) => {
                const points = stroke.points || [];

                if (points.length === 0) {
                    return;
                }

                drawingContext.strokeStyle =
                    stroke.color || "#102448";

                drawingContext.lineWidth = Math.max(
                    2,
                    Number(stroke.size || 0.006) *
                    drawingCanvas.width
                );

                drawingContext.beginPath();

                points.forEach((point, index) => {
                    const x = point.x * drawingCanvas.width;
                    const y = point.y * drawingCanvas.height;

                    if (index === 0) {
                        drawingContext.moveTo(x, y);
                    } else {
                        drawingContext.lineTo(x, y);
                    }
                });

                drawingContext.stroke();
            }
        );
    }

    function drawingPointer(event) {
        return normalizedPointer(event, drawingCanvas);
    }

    drawingCanvas?.addEventListener("pointerdown", (event) => {
        if (!activeExtraPage) {
            return;
        }

        event.preventDefault();
        drawingCanvas.setPointerCapture(event.pointerId);

        drawingStroke = {
            pointerId: event.pointerId,
            color: "#102448",
            size: 0.006,
            points: [drawingPointer(event)],
        };
    });

    drawingCanvas?.addEventListener("pointermove", (event) => {
        if (
            !drawingStroke ||
            drawingStroke.pointerId !== event.pointerId
        ) {
            return;
        }

        event.preventDefault();
        drawingStroke.points.push(drawingPointer(event));

        const draftData = [
            ...(activeExtraPage.drawing_data || []),
            drawingStroke,
        ];

        const originalData = activeExtraPage.drawing_data;
        activeExtraPage.drawing_data = draftData;
        renderExtraDrawing();
        activeExtraPage.drawing_data = originalData;
    });

    function finishDrawingStroke(event) {
        if (
            !drawingStroke ||
            drawingStroke.pointerId !== event.pointerId
        ) {
            return;
        }

        if (drawingStroke.points.length > 1) {
            activeExtraPage.drawing_data = [
                ...(activeExtraPage.drawing_data || []),
                {
                    color: drawingStroke.color,
                    size: drawingStroke.size,
                    points: drawingStroke.points,
                },
            ];

            renderExtraDrawing();
            scheduleExtraPageSave();
        }

        drawingStroke = null;
    }

    drawingCanvas?.addEventListener(
        "pointerup",
        finishDrawingStroke
    );

    drawingCanvas?.addEventListener(
        "pointercancel",
        finishDrawingStroke
    );

    document
        .getElementById("clearExtraPageDrawing")
        ?.addEventListener("click", () => {
            if (!activeExtraPage) {
                return;
            }

            const confirmed = window.confirm(
                "Clear this drawing page?"
            );

            if (!confirmed) {
                return;
            }

            activeExtraPage.drawing_data = [];
            renderExtraDrawing();
            scheduleExtraPageSave();
        });

    essayEditor?.addEventListener(
        "input",
        scheduleExtraPageSave
    );

    document
        .getElementById("closeExtraPageEditor")
        ?.addEventListener("click", () => {
            editorDialog.close();
        });

    editorDialog?.addEventListener("close", () => {
        window.clearTimeout(extraPageSaveTimer);

        if (
            activeExtraPage &&
            activeExtraPage.page_type === "essay"
        ) {
            updateExtraPage(activeExtraPage, {
                essay_text: essayEditor.value,
            });
        }

        if (
            activeExtraPage &&
            activeExtraPage.page_type === "drawing"
        ) {
            updateExtraPage(activeExtraPage, {
                drawing_data:
                    activeExtraPage.drawing_data || [],
            });
        }

        activeExtraPage = null;
    });

    document
        .getElementById("openAnswerPageDialog")
        ?.addEventListener("click", () => {
            answerPageDialog.showModal();
        });

    answerPageDialog
        ?.querySelectorAll("[data-extra-page]")
        .forEach((button) => {
            button.addEventListener("click", async () => {
                answerPageDialog.close();

                await createExtraPage(
                    button.dataset.extraPage
                );
            });
        });

    [
        document.getElementById("mobileOutputUpload"),
        document.getElementById("dialogOutputUpload"),
    ].forEach((input) => {
        input?.addEventListener("change", async () => {
            const file = input.files[0];

            if (!file) {
                return;
            }

            if (answerPageDialog?.open) {
                answerPageDialog.close();
            }

            await createExtraPage("upload", file);
            input.value = "";
        });
    });

    /*
     * Main annotation events
     */

    if (editable) {
        annotationCanvas.addEventListener(
            "pointerdown",
            handlePointerDown
        );

        annotationCanvas.addEventListener(
            "pointermove",
            handlePointerMove
        );

        annotationCanvas.addEventListener(
            "pointerup",
            handlePointerUp
        );

        annotationCanvas.addEventListener(
            "pointercancel",
            handlePointerUp
        );
    }

    previousButton.addEventListener("click", () => {
        changePage(currentPage - 1);
    });

    nextButton.addEventListener("click", () => {
        changePage(currentPage + 1);
    });

    initializeToolButtons();

    /*
     * Load the saved draft before rendering the PDF.
     */

    await loadDraft();

    try {
        const pdfjs = await import(editor.dataset.library);

        pdfjs.GlobalWorkerOptions.workerSrc =
            editor.dataset.worker;

        const pdfResponse = await fetch(
            editor.dataset.pdfUrl,
            {
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    Accept: "application/pdf",
                },
            }
        );

        if (!pdfResponse.ok) {
            throw new Error(
                `The Module PDF request returned ${pdfResponse.status}.`
            );
        }

        const pdfData = new Uint8Array(
            await pdfResponse.arrayBuffer()
        );

        if (pdfData.length === 0) {
            throw new Error("The Module PDF is empty.");
        }

        const signature = new TextDecoder("ascii").decode(
            pdfData.slice(0, 5)
        );

        if (signature !== "%PDF-") {
            const responseType =
                pdfResponse.headers.get("Content-Type") ||
                "unknown content type";

            throw new Error(
                `The Module URL returned ${responseType} instead of PDF data.`
            );
        }

        pdfDocument = await pdfjs.getDocument({
            data: pdfData,
            isEvalSupported: false,
            cMapUrl: `${editor.dataset.assets}cmaps/`,
            cMapPacked: true,
            standardFontDataUrl:
                `${editor.dataset.assets}standard_fonts/`,
            wasmUrl: `${editor.dataset.assets}wasm/`,
        }).promise;

        currentPage = Math.min(
            Math.max(currentPage, 1),
            pdfDocument.numPages
        );

        await renderCurrentPage();
    } catch (error) {
        pageLabel.textContent = "PDF unavailable";

        console.error("PDF.js Module loading failed:", error);

        showError(
            `The PDF.js reader could not load the Module. ${error.message || ""}`
        );
    }

    let previousWidth = stage.clientWidth;

    const observer = new ResizeObserver(() => {
        const currentWidth = stage.clientWidth;

        if (
            currentWidth > 0 &&
            currentWidth !== previousWidth
        ) {
            previousWidth = currentWidth;
            renderCurrentPage();
        }
    });

    observer.observe(stage);

    const submissionForm = document.getElementById(
        "moduleSubmissionForm"
    );

    submissionForm?.addEventListener("submit", async (event) => {
        if (submissionForm.dataset.draftReady === "true") {
            return;
        }

        event.preventDefault();
        window.clearTimeout(saveTimer);

        while (saving) {
            await new Promise((resolve) => {
                window.setTimeout(resolve, 100);
            });
        }

        const saved = await saveAnnotationDraft();
        if (!saved) {
            showError(
                "Your latest changes could not be saved. Please try again before submitting."
            );
            return;
        }

        submissionForm.dataset.draftReady = "true";
        submissionForm.requestSubmit();
    });

}
