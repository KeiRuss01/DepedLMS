// This script only controls the reader and mobile panels.
// Django forms handle saving and submitting answers.

const workspace = document.querySelector(".module-workspace");
const panelButtons = document.querySelectorAll("[data-module-pane]");

panelButtons.forEach((button) => {
    button.addEventListener("click", () => {
        workspace.dataset.visiblePane = button.dataset.modulePane;

        panelButtons.forEach((other) => {
            const selected = other === button;

            other.classList.toggle("btn-primary", selected);
            other.classList.toggle("btn-outline-primary", !selected);
            other.setAttribute("aria-pressed", String(selected));
        });
    });
});

const reader = document.getElementById("pdfReader");

if (reader) {
    startReader();
}

async function startReader() {
    const canvas = document.getElementById("pdfCanvas");
    const viewportBox = reader.querySelector(".pdf-viewport");
    const pageLabel = document.getElementById("pdfPageLabel");
    const errorBox = document.getElementById("pdfError");

    const previous = document.getElementById("pdfPrevious");
    const next = document.getElementById("pdfNext");
    const zoomOut = document.getElementById("pdfZoomOut");
    const zoomIn = document.getElementById("pdfZoomIn");

    let pdf;
    let pageNumber = 1;
    let zoom = 1;
    let rendering = false;
    let renderAgain = false;

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
    }

    function updateButtons() {
        previous.disabled = !pdf || pageNumber <= 1;
        next.disabled = !pdf || pageNumber >= pdf.numPages;
        zoomOut.disabled = !pdf || zoom <= 0.75;
        zoomIn.disabled = !pdf || zoom >= 2;
    }

    async function renderPage() {
        if (!pdf || viewportBox.clientWidth === 0) {
            return;
        }

        // Only one render may use the canvas at a time.
        if (rendering) {
            renderAgain = true;
            return;
        }

        rendering = true;

        try {
            do {
                renderAgain = false;

                if (viewportBox.clientWidth === 0) {
                    break;
                }

                const currentPage = pageNumber;
                const page = await pdf.getPage(currentPage);

                const original = page.getViewport({ scale: 1 });
                const availableWidth = Math.max(
                    100,
                    viewportBox.clientWidth - 24
                );

                const fitScale = availableWidth / original.width;
                const viewport = page.getViewport({
                    scale: fitScale * zoom,
                });

                // Limit pixel density to keep large PDFs manageable.
                const maxPixels = 12000000;
                const pixelRatio = Math.min(
                    window.devicePixelRatio || 1,
                    2,
                    Math.sqrt(
                        maxPixels / (viewport.width * viewport.height)
                    )
                );

                canvas.width = Math.max(
                    1,
                    Math.floor(viewport.width * pixelRatio)
                );

                canvas.height = Math.max(
                    1,
                    Math.floor(viewport.height * pixelRatio)
                );

                canvas.style.width = `${viewport.width}px`;
                canvas.style.height = `${viewport.height}px`;

                await page.render({
                    canvasContext: canvas.getContext("2d"),
                    viewport,
                    transform: [
                        pixelRatio, 0,
                        0, pixelRatio,
                        0, 0,
                    ],
                }).promise;

                pageLabel.textContent =
                    `Page ${currentPage} of ${pdf.numPages}`;

                canvas.setAttribute(
                    "aria-label",
                    `Module PDF page ${currentPage} of ${pdf.numPages}`
                );

                errorBox.hidden = true;

            } while (renderAgain);

        } catch (error) {
            showError(
                "This page could not be displayed. " +
                "You can download the original PDF below."
            );

        } finally {
            rendering = false;
            updateButtons();
        }
    }

    previous.addEventListener("click", () => {
        if (pdf && pageNumber > 1) {
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
        const pdfjs = await import(reader.dataset.library);

        pdfjs.GlobalWorkerOptions.workerSrc = reader.dataset.worker;

        pdf = await pdfjs.getDocument({
            url: reader.dataset.url,
            withCredentials: true,
            isEvalSupported: false,

            cMapUrl: `${reader.dataset.assets}cmaps/`,
            cMapPacked: true,

            standardFontDataUrl:
                `${reader.dataset.assets}standard_fonts/`,

            wasmUrl: `${reader.dataset.assets}wasm/`,
        }).promise;

        updateButtons();
        await renderPage();

        let previousWidth = viewportBox.clientWidth;

        const observer = new ResizeObserver(() => {
            const width = viewportBox.clientWidth;

            if (width > 0 && width !== previousWidth) {
                previousWidth = width;
                renderPage();
            } else if (width === 0) {
                previousWidth = 0;
            }
        });

        observer.observe(viewportBox);

    } catch (error) {
        pageLabel.textContent = "PDF unavailable";

        showError(
            "The reader could not load. Check the local PDF.js files, " +
            "or download the original PDF below."
        );
    }
}