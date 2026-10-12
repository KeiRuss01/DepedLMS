const viewer = document.getElementById("appPdfViewer");

if (viewer) {
    startActivityPdfViewer();
}

async function startActivityPdfViewer() {
    const canvas = document.getElementById("appPdfCanvas");
    const stage = document.getElementById("appPdfStage");
    const loading = document.getElementById("appPdfLoading");
    const errorBox = document.getElementById("appPdfError");
    const pageLabel = document.getElementById("appPdfPageLabel");
    const previous = document.getElementById("appPdfPrevious");
    const next = document.getElementById("appPdfNext");
    const zoomOut = document.getElementById("appPdfZoomOut");
    const zoomIn = document.getElementById("appPdfZoomIn");

    let pdf = null;
    let pageNumber = 1;
    let zoom = 1;
    let renderTask = null;

    function updateControls() {
        previous.disabled = !pdf || pageNumber <= 1;
        next.disabled = !pdf || pageNumber >= pdf.numPages;
        zoomOut.disabled = !pdf || zoom <= 0.75;
        zoomIn.disabled = !pdf || zoom >= 2;
    }

    async function renderPage() {
        if (!pdf || stage.clientWidth === 0) return;

        if (renderTask) {
            renderTask.cancel();
            renderTask = null;
        }

        try {
            const page = await pdf.getPage(pageNumber);
            const original = page.getViewport({ scale: 1 });
            const horizontalPadding = window.innerWidth <= 600 ? 16 : 40;
            const availableWidth = Math.max(160, stage.clientWidth - horizontalPadding);
            const fitScale = availableWidth / original.width;
            const viewport = page.getViewport({ scale: fitScale * zoom });
            const maxPixels = 12000000;
            const pixelRatio = Math.min(
                window.devicePixelRatio || 1,
                2,
                Math.sqrt(maxPixels / (viewport.width * viewport.height))
            );

            canvas.width = Math.max(1, Math.floor(viewport.width * pixelRatio));
            canvas.height = Math.max(1, Math.floor(viewport.height * pixelRatio));
            canvas.style.width = `${viewport.width}px`;
            canvas.style.height = `${viewport.height}px`;

            renderTask = page.render({
                canvasContext: canvas.getContext("2d"),
                viewport,
                transform: [pixelRatio, 0, 0, pixelRatio, 0, 0],
            });
            await renderTask.promise;
            renderTask = null;

            canvas.hidden = false;
            loading.hidden = true;
            errorBox.hidden = true;
            pageLabel.textContent = `Page ${pageNumber} of ${pdf.numPages}`;
            canvas.setAttribute("aria-label", `PDF page ${pageNumber} of ${pdf.numPages}`);
            updateControls();
        } catch (error) {
            if (error?.name === "RenderingCancelledException") return;
            loading.hidden = true;
            errorBox.hidden = false;
        }
    }

    previous.addEventListener("click", () => {
        if (pageNumber > 1) {
            pageNumber -= 1;
            renderPage();
        }
    });
    next.addEventListener("click", () => {
        if (pdf && pageNumber < pdf.numPages) {
            pageNumber += 1;
            renderPage();
        }
    });
    zoomOut.addEventListener("click", () => {
        zoom = Math.max(0.75, zoom - 0.25);
        renderPage();
    });
    zoomIn.addEventListener("click", () => {
        zoom = Math.min(2, zoom + 0.25);
        renderPage();
    });

    try {
        const pdfjs = await import(viewer.dataset.library);
        pdfjs.GlobalWorkerOptions.workerSrc = viewer.dataset.worker;
        pdf = await pdfjs.getDocument({
            url: viewer.dataset.pdfUrl,
            withCredentials: true,
            isEvalSupported: false,
            cMapUrl: `${viewer.dataset.assets}cmaps/`,
            cMapPacked: true,
            standardFontDataUrl: `${viewer.dataset.assets}standard_fonts/`,
            wasmUrl: `${viewer.dataset.assets}wasm/`,
        }).promise;
        await renderPage();

        let previousWidth = stage.clientWidth;
        new ResizeObserver(() => {
            if (stage.clientWidth && stage.clientWidth !== previousWidth) {
                previousWidth = stage.clientWidth;
                renderPage();
            }
        }).observe(stage);
    } catch (error) {
        loading.hidden = true;
        errorBox.hidden = false;
        pageLabel.textContent = "PDF unavailable";
    }
}
