(() => {
    const host = document.getElementById("adobe-dc-view");

    if (!host) {
        return;
    }

    if (window.matchMedia("(max-width: 767.98px)").matches) {
        return;
    }

    let started = false;
    const status = document.getElementById("adobeSaveStatus");
    const submitButton = document.getElementById("submitAnsweredModule");
    const editable = host.dataset.editable === "true";

    function showStatus(message, style = "light") {
        if (!status) return;
        status.textContent = message;
        status.className = `badge text-bg-${style}${style === "light" ? " border" : ""}`;
    }

    async function loadPdf() {
        const response = await fetch(host.dataset.pdfUrl, {
            credentials: "same-origin",
        });
        if (!response.ok) throw new Error("The Module PDF could not be loaded.");
        return response.arrayBuffer();
    }

    function startAdobeViewer() {
        if (started || !window.AdobeDC) return;
        started = true;
        showStatus("Loading PDF...", "light");

        const adobeDCView = new AdobeDC.View({
            clientId: host.dataset.clientId,
            divId: host.id,
        });

        adobeDCView.registerCallback(
            AdobeDC.View.Enum.CallbackType.GET_USER_PROFILE_API,
            () => Promise.resolve({
                code: AdobeDC.View.Enum.ApiResponseCode.SUCCESS,
                data: { userProfile: { name: "LMS user" } },
            }),
            {}
        );

        if (editable && host.dataset.saveUrl) {
            adobeDCView.registerCallback(
                AdobeDC.View.Enum.CallbackType.SAVE_API,
                async (metaData, content) => {
                    showStatus("Saving draft...", "warning");
                    if (submitButton) submitButton.disabled = true;
                    try {
                        const response = await fetch(host.dataset.saveUrl, {
                            method: "POST",
                            credentials: "same-origin",
                            headers: {
                                "Content-Type": "application/pdf",
                                "X-CSRFToken": host.dataset.csrfToken,
                            },
                            body: content,
                        });
                        const result = await response.json();
                        if (!response.ok) throw new Error(result.error || "Draft could not be saved.");
                        showStatus("Draft saved", "success");
                        if (submitButton) submitButton.disabled = false;
                        return {
                            code: AdobeDC.View.Enum.ApiResponseCode.SUCCESS,
                            data: { metaData: Object.assign(metaData, { fileName: result.file_name }) },
                        };
                    } catch (error) {
                        showStatus("Save failed", "danger");
                        throw {
                            code: AdobeDC.View.Enum.ApiResponseCode.FAIL,
                            data: { message: error.message },
                        };
                    }
                },
                {
                    autoSaveFrequency: 5,
                    enableFocusPolling: true,
                    showSaveButton: true,
                }
            );
        }

        adobeDCView.previewFile(
            {
                content: { promise: loadPdf() },
                metaData: {
                    fileName: host.dataset.fileName,
                    id: host.dataset.documentId,
                    hasReadOnlyAccess: !editable,
                },
            },
            {
                embedMode: "FULL_WINDOW",
                defaultViewMode: "FIT_WIDTH",
                showAnnotationTools: editable,
                enableAnnotationAPIs: editable,
                includePDFAnnotations: true,
                enableFormFilling: editable,
                showDownloadPDF: false,
                showPrintPDF: false,
                showDisabledSaveButton: editable,
            }
        ).then(() => {
            if (editable) {
                showStatus(host.dataset.hasDraft === "true" ? "Draft saved" : "Ready to answer", host.dataset.hasDraft === "true" ? "success" : "primary");
            } else {
                showStatus("Read only", "light");
            }
        }).catch(() => showStatus("PDF failed to load", "danger"));
    }

    document.addEventListener("adobe_dc_view_sdk.ready", startAdobeViewer);
    if (window.AdobeDC) startAdobeViewer();
})();
