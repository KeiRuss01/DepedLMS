const editor = document.getElementById("mobileModuleEditor");

if (editor) {
    startMobileModuleEditor(editor);
}

async function startMobileModuleEditor(editor) {
    let editable = editor.dataset.editable === "true";
    const csrfToken = editor.dataset.csrfToken;
    const offlineMode = editor.dataset.storageMode === "offline";
    const moduleId = Number(editor.dataset.moduleId);

    let cachedModule = null;
    let offlineDraftKey = null;

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
    // Change this value to adjust the default size of answers typed on the PDF.
    const DEFAULT_PDF_TEXT_SIZE = 0.018;

    let pdfDocument = null;
    let currentPage = 1;
    let annotations = [];
    let extraPages = [];
    let deletedExtraPages = [];
    let activeTool = "type";
    let activePointer = null;
    let previewAnnotation = null;
    let rendering = false;
    let saveTimer = null;
    let saving = false;
    let saveAgain = false;
    let undoHistory = [];
    let selectedAnnotationId = null;

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
                '<i class="bi bi-device-ssd"></i> Saved on this device';

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

    function essayButtonEnabled(button) {
        return button?.getAttribute("aria-pressed") === "true";
    }

    function setEssayButtonState(button, enabled) {
        if (!button) {
            return;
        }

        button.setAttribute("aria-pressed", String(enabled));
        button.classList.toggle("is-active", enabled);
    }

    function saveEssaySelection() {
        const selection = window.getSelection();
        if (
            !selection ||
            selection.rangeCount === 0 ||
            !essayEditor?.contains(selection.anchorNode)
        ) {
            return;
        }
        savedEssayRange = selection.getRangeAt(0).cloneRange();
    }

    function restoreEssaySelection() {
        if (!savedEssayRange) {
            return false;
        }
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(savedEssayRange);
        return true;
    }

    function updateEssayToolbarState() {
        if (!essayEditor) {
            return;
        }
        setEssayButtonState(
            essayBoldButton,
            document.queryCommandState("bold")
        );
        setEssayButtonState(
            essayItalicButton,
            document.queryCommandState("italic")
        );
    }

    function formatEssaySelection(command) {
        if (!restoreEssaySelection()) {
            essayEditor.focus();
        }
        document.execCommand(command, false, null);
        saveEssaySelection();
        updateEssayToolbarState();
        scheduleExtraPageSave();
    }

    function removeOldFontSizes(fragment) {
        fragment
            .querySelectorAll('font[size], span[style*="font-size"]')
            .forEach((element) => {
                element.replaceWith(...element.childNodes);
            });
    }

    function formatEssaySize() {
        if (!restoreEssaySelection()) {
            essayEditor.focus();
        }

        const selection = window.getSelection();

        if (!selection || selection.rangeCount === 0) {
            return;
        }

        const selectedSize =
            Number(essaySizeSelect?.value) || 16;

        const range = selection.getRangeAt(0);
        const sizeWrapper = document.createElement("span");

        sizeWrapper.style.fontSize = `${selectedSize}px`;

        /*
        * No text is selected.
        * Create an insertion point for newly typed text.
        */
        if (range.collapsed) {
            const marker = document.createTextNode("\u200B");

            sizeWrapper.appendChild(marker);
            range.insertNode(sizeWrapper);

            const newRange = document.createRange();

            newRange.setStart(marker, marker.length);
            newRange.collapse(true);

            selection.removeAllRanges();
            selection.addRange(newRange);

            savedEssayRange = newRange.cloneRange();
        } else {
            /*
            * Text is selected.
            * Remove older nested size wrappers before applying
            * the new exact pixel size.
            */
            const selectedContent = range.extractContents();

            removeOldFontSizes(selectedContent);
            sizeWrapper.appendChild(selectedContent);
            range.insertNode(sizeWrapper);

            const newRange = document.createRange();

            newRange.selectNodeContents(sizeWrapper);

            selection.removeAllRanges();
            selection.addRange(newRange);

            savedEssayRange = newRange.cloneRange();
        }

        essayEditor.focus();
        scheduleExtraPageSave();
    }

    function essayPageChanges() {
        const plainText = essayEditor.innerText
            .replaceAll("\u200B", "")
            .slice(0, 50000);

        const formattedText = essayEditor.innerHTML
            .replaceAll("\u200B", "");

        return {
            essay_text: plainText,
            essay_html: formattedText,
        };
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

    async function prepareModuleStorage() {
        if (!window.N1OfflineDB) {
            throw new Error("The offline database is unavailable.");
        }

        if (!moduleId) {
            throw new Error("No offline module was selected.");
        }

        await window.N1OfflineDB.open();

        let serverData = null;

        if (!offlineMode && editor.dataset.offlineDataUrl) {
            serverData = await requestJson(editor.dataset.offlineDataUrl);
            const serverModule = serverData.module;
            const previousModule = await window.N1OfflineDB.get(
                "cached_modules",
                moduleId
            );

            cachedModule = {
                ...(previousModule || {}),
                ...serverModule,
                id: serverModule.id,
                downloaded_at: previousModule?.downloaded_at || null,
                updated_at: serverModule.published_at || new Date().toISOString()
            };
            await window.N1OfflineDB.put("cached_modules", cachedModule);

            if (window.N1ModuleDownloads?.mergeServerDraft) {
                await window.N1ModuleDownloads.mergeServerDraft(
                    serverModule,
                    serverData.draft
                );
            } else if (serverData.draft) {
                const localId = `${serverModule.student_id}:${serverModule.id}`;
                const localDraft = await window.N1OfflineDB.get(
                    "draft_submissions",
                    localId
                );
                const localPending = ["pending", "failed", "syncing"].includes(
                    localDraft?.sync_status
                );

                if (!localPending) {
                    const serverPages = (
                        serverData.draft.extra_pages || []
                    ).map((page) => ({
                        ...page,
                        local_id: page.local_id || `server-${page.id}`,
                        local_only: false,
                        sync_status: "synced"
                    }));
                    await window.N1OfflineDB.put("draft_submissions", {
                        ...(localDraft || {}),
                        ...serverData.draft,
                        local_id: localId,
                        annotations: serverData.draft.annotations || [],
                        extra_pages: serverPages,
                        sync_status: "synced",
                        sync_error: "",
                        created_at: localDraft?.created_at || new Date().toISOString(),
                        updated_at:
                            serverData.draft.server_updated_at ||
                            new Date().toISOString()
                    });
                }
            }
        } else {
            cachedModule = await window.N1OfflineDB.get(
                "cached_modules",
                moduleId
            );
        }

        const identity = await window.N1OfflineDB.get(
            "device_identity",
            "current"
        );

        if (!cachedModule || (offlineMode && !cachedModule.pdf_blob)) {
            throw new Error(
                "This module has not been downloaded on this device."
            );
        }

        if (offlineMode && (
            String(identity?.account_role || "").toLowerCase() !==
                "student" ||
            !identity?.user_id ||
            !cachedModule.user_id ||
            Number(cachedModule.user_id) !== Number(identity.user_id)
        )) {
            throw new Error(
                "This downloaded module belongs to another account. Sign in with the Student account that downloaded it."
            );
        }

        if (!cachedModule.student_id) {
            throw new Error(
                "Please download this module again before answering offline."
            );
        }

        const backToClassModules = document.getElementById(
            "backToClassModules"
        );

        if (backToClassModules && cachedModule.class_id) {
            backToClassModules.href = (
                `/classroom/classes/${cachedModule.class_id}/?tab=modules`
            );
        }

        offlineDraftKey = (
            `${cachedModule.student_id}:${cachedModule.id}`
        );

        const title = document.getElementById("mobileEditorTitle");

        if (title) {
            title.textContent = cachedModule.title;
        }

        const deadlineClosed = Boolean(
            cachedModule.due_at &&
            Date.now() > new Date(cachedModule.due_at).getTime() &&
            !cachedModule.allow_late
        );

        if (deadlineClosed) {
            editable = false;

            disableEditor(
                "The deadline has passed. This downloaded module is now read only."
            );
        }
    }

    async function queueDraftSync() {
        if (!offlineDraftKey || !cachedModule) {
            return;
        }

        const queue = await window.N1OfflineDB.getAll("offline_queue");
        const finalSubmissionQueued = queue.some((item) => (
            item.action_type === "module_submission" &&
            item.draft_local_id === offlineDraftKey &&
            ["pending", "failed", "syncing"].includes(item.status)
        ));

        if (finalSubmissionQueued) {
            return;
        }

        const existing = queue.find((item) => (
            item.action_type === "module_draft_sync" &&
            item.draft_local_id === offlineDraftKey
        ));
        const now = new Date().toISOString();

        await window.N1OfflineDB.put("offline_queue", {
            ...(existing || {}),
            action_type: "module_draft_sync",
            target_table: "module_submission",
            target_id: cachedModule.id,
            draft_local_id: offlineDraftKey,
            user_id: cachedModule.user_id || null,
            status: "pending",
            retry_count: existing?.retry_count || 0,
            error_message: "",
            created_at: existing?.created_at || now,
            updated_at: now,
            synced_at: null
        });
    }

    async function loadDraft() {
        if (!editable) {
            const previewState = document.getElementById(
                "moduleReadOnlyDraftState"
            );

            if (previewState) {
                try {
                    const data = JSON.parse(previewState.textContent);
                    annotations = Array.isArray(data.annotations)
                        ? data.annotations
                        : [];
                    extraPages = Array.isArray(data.extra_pages)
                        ? data.extra_pages
                        : [];
                    currentPage = Number(data.current_page) || 1;
                    setDraftStatus("Draft preview");
                } catch (error) {
                    console.error("Draft preview loading failed:", error);
                    showError("The Student draft preview could not be loaded.");
                }
            }
            return;
        }

        try {
            let data;

            if (offlineDraftKey && window.N1OfflineDB) {
                const localDraft = await window.N1OfflineDB.get(
                    "draft_submissions",
                    offlineDraftKey
                );

                if (!localDraft) {
                    annotations = [];
                    extraPages = [];
                    currentPage = 1;

                    renderExtraPages();
                    updateUndoButton();
                    setDraftStatus("Not saved yet");
                    return;
                }

                data = {
                    annotations: localDraft.annotations || [],
                    extra_pages: localDraft.extra_pages || [],
                    deleted_extra_pages:
                        localDraft.deleted_extra_pages || [],
                    current_page: localDraft.current_page || 1,
                    editable: true,
                    draft_saved_at: localDraft.updated_at
                };
            } else {
                data = await requestJson(
                    editor.dataset.draftStateUrl
                );
            }

            annotations = Array.isArray(data.annotations)
                ? data.annotations
                : [];

            extraPages = Array.isArray(data.extra_pages)
                ? data.extra_pages
                : [];
            deletedExtraPages = Array.isArray(data.deleted_extra_pages)
                ? data.deleted_extra_pages
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
            console.error("Draft loading failed:", error);
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
            if (offlineDraftKey && cachedModule && window.N1OfflineDB) {
                if (!window.N1OfflineDB) {
                    throw new Error(
                        "The offline database is unavailable."
                    );
                }

                if (!offlineDraftKey || !cachedModule) {
                    throw new Error(
                        "The downloaded module information is incomplete."
                    );
                }

                const existingDraft = await window.N1OfflineDB.get(
                    "draft_submissions",
                    offlineDraftKey
                );

                const savedAt = new Date().toISOString();

                await window.N1OfflineDB.put(
                    "draft_submissions",
                    {
                        ...(existingDraft || {}),
                        local_id: offlineDraftKey,
                        module_id: cachedModule.id,
                        student_id: cachedModule.student_id,
                        user_id: cachedModule.user_id || null,
                        class_id: cachedModule.class_id,
                        current_page: currentPage,
                        annotations: annotations,
                        extra_pages: extraPages,
                        deleted_extra_pages: deletedExtraPages,
                        status: "draft",
                        sync_status: "pending",
                        created_at: (
                            existingDraft?.created_at || savedAt
                        ),
                        updated_at: savedAt
                    }
                );

                await queueDraftSync();

                if (offlineSubmitButton) {
                    offlineSubmitButton.disabled = false;
                    offlineSubmitButton.textContent =
                        "Submit module";
                }
                if (navigator.onLine && window.N1OfflineSync) {
                    const result = await window.N1OfflineSync.syncNow();
                    if (result?.failed) {
                        setDraftStatus("Waiting to sync");
                    }
                }
            } else {
                await requestJson(
                    editor.dataset.annotationSaveUrl,
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            current_page: currentPage,
                            annotations
                        })
                    }
                );
            }

            const syncedDraft = offlineDraftKey
                ? await window.N1OfflineDB.get(
                    "draft_submissions",
                    offlineDraftKey
                )
                : null;
            if (syncedDraft?.sync_status === "synced") {
                extraPages = Array.isArray(syncedDraft.extra_pages)
                    ? syncedDraft.extra_pages
                    : extraPages;
                deletedExtraPages = Array.isArray(
                    syncedDraft.deleted_extra_pages
                ) ? syncedDraft.deleted_extra_pages : [];
                renderExtraPages();
                draftStatus.classList.add("is-saved");
                draftStatus.innerHTML =
                    '<i class="bi bi-cloud-check-fill"></i> Draft synchronized';
            } else {
                setDraftStatus("Saved", "saved");
            }
            clearError();
            return true;
        } catch (error) {
            console.error("Draft saving failed:", error);
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
                11,
                Number(annotation.size || DEFAULT_PDF_TEXT_SIZE) * height
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
                    size: DEFAULT_PDF_TEXT_SIZE,
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
    }

    function disableEditor(message) {
        document
            .querySelectorAll(
                "[data-mobile-tool], " +
                "#openAnswerPageDialog, " +
                "#mobileOutputUpload, " +
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

    const essaySection = document.getElementById(
    "extraPageEssaySection"
    );

    const essaySizeSelect = document.getElementById(
        "extraPageEssaySize"
    );

    const essayBoldButton = document.getElementById(
        "extraPageEssayBold"
    );

    const essayItalicButton = document.getElementById(
        "extraPageEssayItalic"
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
    let savedEssayRange = null;

    async function createExtraPage(pageType, uploadedFile = null) {
        if (!editable) {
            return;
        }

        const allowedPageTypes = [
            "essay",
            "drawing",
            "upload",
        ];

        if (!allowedPageTypes.includes(pageType)) {
            showError("Invalid answer page type.");
            return;
        }

        if (pageType === "upload" && !uploadedFile) {
            showError("Please select a PDF, JPG, or PNG file.");
            return;
        }

        if (uploadedFile) {
            const allowedTypes = [
                "application/pdf",
                "image/jpeg",
                "image/png",
            ];

            const maximumFileSize = 20 * 1024 * 1024;

            if (!allowedTypes.includes(uploadedFile.type)) {
                showError("Only PDF, JPG, and PNG files are allowed.");
                return;
            }

            if (uploadedFile.size > maximumFileSize) {
                showError("The selected file must not exceed 20 MB.");
                return;
            }
        }

        /*
        * When offline, save the new answer page directly into IndexedDB.
        * Do not call fetch(), because the Django server is unavailable.
        */
        if (offlineDraftKey && cachedModule) {
            if (!offlineDraftKey || !cachedModule) {
                showError(
                    "The downloaded module information is incomplete."
                );
                return;
            }

            const localPageId = `local-${Date.now()}-${createId()}`;

            const localPage = {
                id: localPageId,
                local_id: localPageId,
                local_only: true,
                sync_status: "pending",

                page_type: pageType,
                title:
                    pageType === "essay"
                        ? "Answer page"
                        : pageType === "drawing"
                            ? "Drawing page"
                            : uploadedFile.name,

                related_pdf_page: currentPage,
                position: extraPages.length + 1,

                essay_text: "",
                drawing_data: [],
                caption: "",

                uploaded_blob: uploadedFile || null,
                uploaded_file_name: uploadedFile
                    ? uploadedFile.name
                    : "",
                uploaded_file_type: uploadedFile
                    ? uploadedFile.type
                    : "",
                uploaded_file_size: uploadedFile
                    ? uploadedFile.size
                    : 0,

                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
            };

            extraPages.push(localPage);

            renderExtraPages();

            const saved = await saveAnnotationDraft();

            if (!saved) {
                showError(
                    "The answer page could not be saved on this device."
                );
                return;
            }

            clearError();
            setDraftStatus("Saved on this device");

            if (pageType === "essay" || pageType === "drawing") {
                const savedPage = extraPages.find((page) => (
                    page.id === localPageId ||
                    page.local_id === localPageId
                ));
                openExtraPageEditor(savedPage || localPage);
            }

            return;
        }

        /*
        * Online mode: send the new page to Django.
        */
        try {
            const formData = new FormData();

            formData.append("page_type", pageType);
            formData.append(
                "related_pdf_page",
                String(currentPage)
            );
            formData.append(
                "position",
                String(extraPages.length + 1)
            );

            if (uploadedFile) {
                formData.append("file", uploadedFile);
                formData.append("title", uploadedFile.name);
            }

            const response = await fetch(
                editor.dataset.extraPageCreateUrl,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": csrfToken,
                        Accept: "application/json",
                    },
                    body: formData,
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error || "The answer page could not be created."
                );
            }

            extraPages.push(data.page);
            renderExtraPages();
            clearError();

            if (pageType === "essay" || pageType === "drawing") {
                openExtraPageEditor(data.page);
            }
        } catch (error) {
            showError(
                error.message ||
                "The answer page could not be created."
            );
        }
    }

    async function updateExtraPage(page, changes) {
        setDraftStatus("Saving", "saving");

        try {
            if (offlineDraftKey && cachedModule) {
                const index = extraPages.findIndex(
                    (item) => item.id === page.id
                );

                if (index === -1) {
                    throw new Error(
                        "The local answer page could not be found."
                    );
                }

                const updatedPage = {
                    ...extraPages[index],
                    ...changes,
                    sync_status: "pending",
                    updated_at: new Date().toISOString()
                };

                extraPages[index] = updatedPage;
                activeExtraPage = updatedPage;

                renderExtraPages();

                const saved = await saveAnnotationDraft();

                if (!saved && !saving) {
                    throw new Error(
                        "The answer page could not be saved locally."
                    );
                }

                setDraftStatus("Saved", "saved");
                clearError();
                return;
            }

            const data = await requestJson(
                page.update_url,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(changes)
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
            console.error("Answer-page update failed:", error);
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
                updateExtraPage(
                    activeExtraPage,
                    essayPageChanges()
                );
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
            if (offlineDraftKey && cachedModule) {
                if (page.local_only === false && page.delete_url) {
                    deletedExtraPages.push({
                        id: page.id,
                        delete_url: page.delete_url
                    });
                }

                extraPages = extraPages.filter(
                    (item) => item.id !== page.id
                );

                if (
                    activeExtraPage &&
                    activeExtraPage.id === page.id
                ) {
                    activeExtraPage = null;

                    if (editorDialog?.open) {
                        editorDialog.close();
                    }
                }

                renderExtraPages();

                const saved = await saveAnnotationDraft();

                if (!saved && !saving) {
                    throw new Error(
                        "The answer page could not be removed locally."
                    );
                }

                setDraftStatus("Saved", "saved");
                clearError();
                return;
            }

            await requestJson(page.delete_url, {
                method: "POST"
            });

            extraPages = extraPages.filter(
                (item) => item.id !== page.id
            );

            renderExtraPages();
            setDraftStatus("Saved", "saved");
            clearError();
        } catch (error) {
            console.error("Answer-page deletion failed:", error);
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

            if (
                page.page_type === "upload" &&
                (page.uploaded_blob || page.file_url)
            ) {
                const openLink = document.createElement("a");

                if (page.uploaded_blob) {
                    const objectUrl = URL.createObjectURL(
                        page.uploaded_blob
                    );

                    openLink.href = objectUrl;

                    openLink.addEventListener(
                        "click",
                        () => {
                            window.setTimeout(() => {
                                URL.revokeObjectURL(objectUrl);
                            }, 60000);
                        },
                        { once: true }
                    );
                } else {
                    openLink.href = page.file_url;
                }

                openLink.target = "_blank";
                openLink.rel = "noopener";
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

        essaySection.hidden =
            activeExtraPage.page_type !== "essay";

        drawingEditor.hidden =
            activeExtraPage.page_type !== "drawing";

        if (activeExtraPage.page_type === "essay") {
            if (activeExtraPage.essay_html) {
                essayEditor.innerHTML = activeExtraPage.essay_html;
            } else {
                essayEditor.textContent =
                    activeExtraPage.essay_text || "";

                let legacyHtml = essayEditor.innerHTML;
                if (activeExtraPage.essay_bold) {
                    legacyHtml = `<b>${legacyHtml}</b>`;
                }
                if (activeExtraPage.essay_italic) {
                    legacyHtml = `<i>${legacyHtml}</i>`;
                }
                if (Number(activeExtraPage.essay_font_size) !== 16) {
                    const size = Number(activeExtraPage.essay_font_size) || 16;
                    legacyHtml = `<span style="font-size: ${size}px">${legacyHtml}</span>`;
                }
                essayEditor.innerHTML = legacyHtml;
            }

            savedEssayRange = null;
            essaySizeSelect.value = "16";
            setEssayButtonState(essayBoldButton, false);
            setEssayButtonState(essayItalicButton, false);
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
        () => {
            saveEssaySelection();
            updateEssayToolbarState();
            scheduleExtraPageSave();
        }
    );

    essayEditor?.addEventListener("keyup", () => {
        saveEssaySelection();
        updateEssayToolbarState();
    });

    essayEditor?.addEventListener("mouseup", () => {
        saveEssaySelection();
        updateEssayToolbarState();
    });

    essaySizeSelect?.addEventListener("pointerdown", saveEssaySelection);
    essaySizeSelect?.addEventListener("change", () => {
        formatEssaySize();
    });

    essayBoldButton?.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        saveEssaySelection();
    });
    essayBoldButton?.addEventListener("click", () => {
        formatEssaySelection("bold");
    });

    essayItalicButton?.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        saveEssaySelection();
    });
    essayItalicButton?.addEventListener("click", () => {
        formatEssaySelection("italic");
    });

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
            updateExtraPage(
                activeExtraPage,
                essayPageChanges()
            );
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

    if (editable || offlineMode) {
        try {
            await prepareModuleStorage();
        } catch (error) {
            pageLabel.textContent = "Module unavailable";
            showError(error.message);
            return;
        }
    }

    await loadDraft();

    try {
        const pdfjs = await import(editor.dataset.library);

        pdfjs.GlobalWorkerOptions.workerSrc =
            editor.dataset.worker;

        let pdfData;
        let responseType = "cached PDF";

        if (offlineMode) {
            pdfData = new Uint8Array(
                await cachedModule.pdf_blob.arrayBuffer()
            );
        } else {
            try {
                const pdfResponse = await fetch(
                    editor.dataset.pdfUrl,
                    {
                        credentials: "same-origin",
                        cache: "no-store",
                        headers: {
                            Accept: "application/pdf"
                        }
                    }
                );

                if (!pdfResponse.ok) {
                    throw new Error(
                        `The Module PDF request returned ${pdfResponse.status}.`
                    );
                }

                responseType = (
                    pdfResponse.headers.get("Content-Type") ||
                    "unknown content type"
                );

                pdfData = new Uint8Array(
                    await pdfResponse.arrayBuffer()
                );

                if (cachedModule && window.N1OfflineDB) {
                    cachedModule.pdf_blob = new Blob(
                        [pdfData],
                        { type: "application/pdf" }
                    );
                    cachedModule.pdf_type = "application/pdf";
                    cachedModule.pdf_size = pdfData.byteLength;
                    cachedModule.downloaded_at = new Date().toISOString();
                    await window.N1OfflineDB.put(
                        "cached_modules",
                        cachedModule
                    );
                }
            } catch (networkError) {
                if (!cachedModule?.pdf_blob) {
                    throw networkError;
                }

                responseType = "cached PDF";
                pdfData = new Uint8Array(
                    await cachedModule.pdf_blob.arrayBuffer()
                );
                setDraftStatus("Working from saved copy");
            }
        }

        if (pdfData.length === 0) {
            throw new Error("The Module PDF is empty.");
        }

        const signature = new TextDecoder("ascii").decode(
            pdfData.slice(0, 5)
        );

        if (signature !== "%PDF-") {
            throw new Error(
                `The Module contains ${responseType} instead of PDF data.`
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

    if ("ResizeObserver" in window) {
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
    } else {
        window.addEventListener("resize", () => {
            const currentWidth = stage.clientWidth;

            if (
                currentWidth > 0 &&
                currentWidth !== previousWidth
            ) {
                previousWidth = currentWidth;
                renderCurrentPage();
            }
        });
    }

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

        if (offlineDraftKey && navigator.onLine) {
            const localDraft = await window.N1OfflineDB.get(
                "draft_submissions",
                offlineDraftKey
            );
            if (localDraft?.sync_status !== "synced") {
                showError(
                    "Your draft is safe on this device but has not synchronized yet. Try submitting again after synchronization finishes."
                );
                return;
            }
        }

        submissionForm.dataset.draftReady = "true";
        submissionForm.requestSubmit();
    });

    const offlineSubmitButton = document.getElementById(
        "queueOfflineSubmission"
    );

    async function updateOfflineSubmitButton() {
        if (!offlineSubmitButton || !offlineDraftKey) {
            return;
        }

        const draft = await window.N1OfflineDB.get(
            "draft_submissions",
            offlineDraftKey
        );

        if (draft?.status === "submitted") {
            offlineSubmitButton.disabled = true;
            offlineSubmitButton.textContent = "Submitted";
        } else if (draft?.sync_status === "failed") {
            offlineSubmitButton.disabled = false;
            offlineSubmitButton.textContent = "Retry submission";
        } else if (draft?.status === "queued") {
            offlineSubmitButton.disabled = false;
            offlineSubmitButton.textContent = navigator.onLine
                ? "Synchronize submission"
                : "Queued for submission";
        }
    }

    offlineSubmitButton?.addEventListener("click", async () => {
        if (!offlineMode || !offlineDraftKey || !cachedModule) {
            showError("The offline module is not ready for submission.");
            return;
        }

        window.clearTimeout(saveTimer);

        while (saving) {
            await new Promise((resolve) => {
                window.setTimeout(resolve, 100);
            });
        }

        const saved = await saveAnnotationDraft();
        if (!saved) {
            showError(
                "Your latest offline changes could not be saved. Please try again."
            );
            return;
        }

        const draft = await window.N1OfflineDB.get(
            "draft_submissions",
            offlineDraftKey
        );

        const hasAnnotations = Array.isArray(draft?.annotations) &&
            draft.annotations.length > 0;
        const hasExtraPages = Array.isArray(draft?.extra_pages) &&
            draft.extra_pages.length > 0;

        if (!hasAnnotations && !hasExtraPages) {
            showError(
                "Add an answer, drawing, page, or photo before submitting."
            );
            return;
        }

        if (!window.confirm(
            "Submit this complete module? Draft synchronization alone will not submit it."
        )) {
            return;
        }

        const queueItems = await window.N1OfflineDB.getAll(
            "offline_queue"
        );

        for (const item of queueItems) {
            if (
                item.action_type === "module_draft_sync" &&
                item.draft_local_id === offlineDraftKey
            ) {
                await window.N1OfflineDB.remove(
                    "offline_queue",
                    item.queue_id
                );
            }
        }
        
        let existingQueue = queueItems.find((item) => (
            item.action_type === "module_submission" &&
            item.draft_local_id === offlineDraftKey &&
            item.status !== "completed"
        ));

        if (existingQueue) {
            /*
            * Unlock an old queue record before retrying.
            */
            existingQueue.status = "pending";
            existingQueue.error_message = "";
            existingQueue.updated_at =
                new Date().toISOString();

            await window.N1OfflineDB.put(
                "offline_queue",
                existingQueue
            );
        } else {
            existingQueue = {
                action_type: "module_submission",
                target_table: "module_submission",
                target_id: cachedModule.id,
                draft_local_id: offlineDraftKey,
                user_id: cachedModule.user_id || null,
                status: "pending",
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                synced_at: null,
                retry_count: 0,
                error_message: ""
            };

            await window.N1OfflineDB.put(
                "offline_queue",
                existingQueue
            );
        }

        draft.status = "queued";
        draft.sync_status = "pending";
        draft.updated_at = new Date().toISOString();

        await window.N1OfflineDB.put(
            "draft_submissions",
            draft
        );

        offlineSubmitButton.textContent = navigator.onLine
            ? "Synchronizing..."
            : "Queued for submission";
        setDraftStatus(
            navigator.onLine
                ? "Synchronizing submission..."
                : "Submission queued on this device"
        );
        clearError();

        if (navigator.onLine && window.N1OfflineSync) {
            try {
                const syncResult = await window.N1OfflineSync.syncNow();
                if (syncResult?.failed) {
                    offlineSubmitButton.disabled = false;
                    offlineSubmitButton.textContent = "Retry submission";
                }
            } catch (error) {
                offlineSubmitButton.disabled = false;
                offlineSubmitButton.textContent = "Retry submission";
                showError(error.message || "Synchronization failed.");
            }
        }
    });

    window.addEventListener("n1:offline-sync", async (event) => {
        if (
            event.detail?.status === "draft-synced" &&
            event.detail?.draftLocalId === offlineDraftKey
        ) {
            draftStatus.classList.add("is-saved");
            draftStatus.innerHTML =
                '<i class="bi bi-cloud-check-fill"></i> Draft synchronized';
            clearError();
        }

        if (
            !offlineSubmitButton ||
            event.detail?.draftLocalId !== offlineDraftKey
        ) {
            return;
        }

        if (event.detail.status === "completed") {
            offlineSubmitButton.disabled = true;
            offlineSubmitButton.textContent = "Submitted";
            setDraftStatus("Submitted and synchronized");
            clearError();
        } else if (event.detail.status === "failed") {
            offlineSubmitButton.disabled = false;
            offlineSubmitButton.textContent = "Retry submission";
            showError(
                event.detail.message ||
                "The queued submission could not be synchronized."
            );
        }
    });

    await updateOfflineSubmitButton();

}
