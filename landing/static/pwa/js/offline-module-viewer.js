(() => {
    "use strict";

    const moduleLibrary = document.querySelector("#moduleLibrary");
    const moduleViewer = document.querySelector("#moduleViewer");
    const moduleList = document.querySelector("#moduleList");
    const emptyModules = document.querySelector("#emptyModules");
    const connectionStatus = document.querySelector("#connectionStatus");
    const viewerTitle = document.querySelector("#viewerTitle");
    const viewerClass = document.querySelector("#viewerClass");
    const viewerInstructions = document.querySelector(
        "#viewerInstructions"
    );
    const viewerMessage = document.querySelector("#viewerMessage");
    const pdfPages = document.querySelector("#pdfPages");
    const backButton = document.querySelector("#backToLibrary");
    const backToClassModules = document.querySelector(
        "#backToClassModules"
    );
    let currentIdentity = null;

    function classModulesUrl(classId) {
        const numericClassId = Number(classId);

        return numericClassId
            ? `/classroom/classes/${numericClassId}/?tab=modules`
            : "/classroom/classes/";
    }

    function updateClassBackLink(classId) {
        if (!backToClassModules) {
            return;
        }

        backToClassModules.href = classModulesUrl(classId);
        backToClassModules.innerHTML = classId
            ? '<i class="bi bi-arrow-left me-1"></i> Back to class modules'
            : '<i class="bi bi-arrow-left me-1"></i> Back to classes';
    }

    function canAccessModule(module) {
        return Boolean(
            module &&
            currentIdentity?.user_id &&
            String(currentIdentity.account_role || "").toLowerCase() ===
                "student" &&
            module.user_id &&
            Number(module.user_id) === Number(currentIdentity.user_id)
        );
    }

    function updateConnectionStatus() {
        if (navigator.onLine) {
            connectionStatus.textContent = "Online";
            connectionStatus.className = "badge text-bg-success";
        } else {
            connectionStatus.textContent = "Offline";
            connectionStatus.className = "badge text-bg-warning";
        }
    }

    function formatDate(value) {
        if (!value) {
            return "No deadline";
        }

        return new Intl.DateTimeFormat("en-PH", {
            dateStyle: "medium",
            timeStyle: "short"
        }).format(new Date(value));
    }

    function formatSize(bytes) {
        if (!bytes) {
            return "";
        }

        if (bytes < 1024 * 1024) {
            return `${Math.round(bytes / 1024)} KB`;
        }

        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    function createModuleCard(module) {
        const column = document.createElement("div");
        column.className = "col-md-6";

        const card = document.createElement("article");
        card.className = "module-card h-100 p-3";

        const term = document.createElement("div");
        term.className = "small text-primary";
        term.textContent = `Term ${module.term}${
            module.week ? ` · ${module.week}` : ""
        }`;

        const title = document.createElement("h2");
        title.className = "h5 mt-2";
        title.textContent = module.title;

        const classroom = document.createElement("p");
        classroom.className = "text-muted mb-2";
        classroom.textContent = module.class_name;

        const details = document.createElement("p");
        details.className = "small mb-3";
        details.textContent = (
            `Due: ${formatDate(module.due_at)}` +
            (module.pdf_size
                ? ` · ${formatSize(module.pdf_size)}`
                : "")
        );

        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-primary";
        button.textContent = "View offline";
        button.addEventListener("click", () => {
            openModule(module.id);
        });

        const answerButton = document.createElement("a");
        answerButton.className = "btn btn-outline-primary";
        answerButton.textContent = "Answer offline";
        answerButton.href = (
            `/offline/modules/editor/?module=${module.id}`
        );

        const deadlineClosed = Boolean(
            module.due_at &&
            Date.now() > new Date(module.due_at).getTime() &&
            !module.allow_late
        );

        if (deadlineClosed) {
            answerButton.classList.add("disabled");
            answerButton.setAttribute("aria-disabled", "true");
            answerButton.removeAttribute("href");
            answerButton.textContent = "Deadline closed";
        }

        const actions = document.createElement("div");
        actions.className = "d-flex flex-wrap gap-2";

        actions.append(button, answerButton);
        card.append(term, title, classroom, details, actions);
        column.append(card);

        return column;
    }

    async function loadLibrary() {
        const allModules = await window.N1OfflineDB.getAll(
            "cached_modules"
        );
        currentIdentity = await window.N1OfflineDB.get(
            "device_identity",
            "current"
        );
        const modules = allModules.filter(canAccessModule);

        const requestedClassId = new URLSearchParams(
            window.location.search
        ).get("class");

        updateClassBackLink(
            requestedClassId || modules[0]?.class_id
        );

        modules.sort((first, second) => {
            return String(first.title).localeCompare(
                String(second.title)
            );
        });

        moduleList.replaceChildren();
        emptyModules.hidden = modules.length !== 0;

        if (!modules.length) {
            emptyModules.textContent =
                String(currentIdentity?.account_role || "").toLowerCase() ===
                    "student"
                    ? "No modules are downloaded for this Student account."
                    : "Downloaded modules are available only to the Student account that saved them.";
        }

        modules.forEach((module) => {
            moduleList.append(createModuleCard(module));
        });
    }

    async function renderPdf(pdfBlob) {
        const pdfjs = await import(document.body.dataset.pdfLibrary);

        pdfjs.GlobalWorkerOptions.workerSrc =
            document.body.dataset.pdfWorker;

        const pdfData = new Uint8Array(
            await pdfBlob.arrayBuffer()
        );

        const documentTask = pdfjs.getDocument({
            data: pdfData,
            isEvalSupported: false
        });

        const pdf = await documentTask.promise;
        pdfPages.replaceChildren();

        for (let pageNumber = 1;
             pageNumber <= pdf.numPages;
             pageNumber += 1) {

            const page = await pdf.getPage(pageNumber);
            const originalViewport = page.getViewport({ scale: 1 });

            const availableWidth = Math.min(
                pdfPages.clientWidth - 16,
                1000
            );

            const scale = Math.max(
                0.5,
                availableWidth / originalViewport.width
            );

            const viewport = page.getViewport({ scale });
            const pixelRatio = window.devicePixelRatio || 1;

            const canvas = document.createElement("canvas");
            const context = canvas.getContext("2d");

            canvas.className = "pdf-page";
            canvas.width = Math.floor(
                viewport.width * pixelRatio
            );
            canvas.height = Math.floor(
                viewport.height * pixelRatio
            );
            canvas.style.width = `${viewport.width}px`;
            canvas.style.height = `${viewport.height}px`;

            pdfPages.append(canvas);

            await page.render({
                canvasContext: context,
                viewport,
                transform: pixelRatio === 1
                    ? null
                    : [pixelRatio, 0, 0, pixelRatio, 0, 0]
            }).promise;
        }
    }

    async function openModule(moduleId) {
        const module = await window.N1OfflineDB.get(
            "cached_modules",
            Number(moduleId)
        );

        if (!canAccessModule(module) || !module.pdf_blob) {
            alert("This module is not available for the current Student account.");
            return;
        }

        updateClassBackLink(module.class_id);

        moduleLibrary.hidden = true;
        moduleViewer.hidden = false;
        pdfPages.replaceChildren();

        viewerTitle.textContent = module.title;
        viewerClass.textContent = (
            `${module.class_name} · Term ${module.term}`
        );
        viewerInstructions.textContent = (
            module.instructions || "No additional instructions."
        );

        viewerMessage.hidden = false;
        viewerMessage.className = "alert alert-info";
        viewerMessage.textContent = "Loading module…";

        try {
            await renderPdf(module.pdf_blob);
            viewerMessage.hidden = true;
        } catch (error) {
            console.error("Offline PDF error:", error);
            viewerMessage.hidden = false;
            viewerMessage.className = "alert alert-danger";
            viewerMessage.textContent = (
                "The downloaded PDF could not be displayed."
            );
        }

        window.scrollTo({ top: 0 });
    }

    backButton.addEventListener("click", () => {
        moduleViewer.hidden = true;
        moduleLibrary.hidden = false;
        pdfPages.replaceChildren();
        window.scrollTo({ top: 0 });
    });

    window.addEventListener("online", updateConnectionStatus);
    window.addEventListener("offline", updateConnectionStatus);

    document.addEventListener("DOMContentLoaded", async () => {
        updateConnectionStatus();

        try {
            await window.N1OfflineDB.open();
            await loadLibrary();

            const requestedModuleId = new URLSearchParams(
                window.location.search
            ).get("module");

            if (requestedModuleId) {
                await openModule(requestedModuleId);
            }
        } catch (error) {
            console.error("Offline library error:", error);
            emptyModules.hidden = false;
            emptyModules.textContent = (
                "Downloaded modules could not be displayed. Reload this page and try again."
            );
        }
    });
})();
