(() => {
    "use strict";
    const params = new URLSearchParams(location.search);
    const classId = Number(params.get("class"));
    const term = String(params.get("term") || "1");
    const table = document.getElementById("offlineGradeTable");
    const head = document.getElementById("gradeTableHead");
    const body = document.getElementById("gradeTableBody");
    const empty = document.getElementById("emptyGradebook");
    const message = document.getElementById("gradebookMessage");
    const syncButton = document.getElementById("syncGradesButton");
    const connection = document.getElementById("connectionStatus");
    const addButton = document.getElementById("addOfflineActivityButton");
    const activityForm = document.getElementById("offlineActivityForm");
    const activityModal = document.getElementById("offlineActivityModal");
    const activityError = document.getElementById("offlineActivityError");

    function status() {
        connection.textContent = navigator.onLine ? "Online" : "Offline";
        connection.classList.toggle("offline", !navigator.onLine);
    }
    function show(text, type="info") { message.textContent = text; message.className = `alert alert-${type}`; }
    function localId(itemId, studentId) { return `grade:${classId}:${term}:${itemId}:${studentId}`; }

    async function queueSync() {
        const queue = await N1OfflineDB.getAll("offline_queue");
        const old = queue.find((item) => item.action_type === "score_sync" && Number(item.class_id) === classId && String(item.term) === term && ["pending", "failed"].includes(item.status));
        const now = new Date().toISOString();
        await N1OfflineDB.put("offline_queue", {...(old || {}), action_type:"score_sync", target_table:"grade_score", class_id:classId, term, status:"pending", retry_count:Number(old?.retry_count || 0), error_message:"", created_at:old?.created_at || now, updated_at:now});
    }

    async function addActivity(event) {
        event.preventDefault();
        activityError.hidden = true;
        const cachedClass = await N1OfflineDB.get("cached_classes", classId);
        if (!cachedClass) return;
        const title = document.getElementById("offlineActivityTitle").value.trim();
        const component = document.getElementById("offlineActivityComponent").value;
        const maximum = Number(document.getElementById("offlineActivityMaximum").value);
        if (!title || !Number.isFinite(maximum) || maximum <= 0) {
            activityError.textContent = "Enter a title and a highest possible score greater than zero.";
            activityError.hidden = false;
            return;
        }
        const tempId = -Date.now();
        const now = new Date().toISOString();
        const labels = {written_work:"Written Work", performance_task:"Performance Task", assessment:"Term Assessment"};
        const item = {local_id:`${classId}:${term}:local:${tempId}`, item_id:tempId, class_id:classId, term, component, component_label:labels[component], title, position:999999, highest_possible_score:maximum, offline_pending:true, updated_at:now};
        await N1OfflineDB.put("cached_grade_items", item);
        await N1OfflineDB.put("offline_queue", {action_type:"grade_item_create", target_table:"grade_item", class_id:classId, term, temp_item_id:tempId, payload:{title, component, highest_possible_score:maximum, term}, status:"pending", retry_count:0, error_message:"", created_at:now, updated_at:now});
        activityForm.reset();
        bootstrap.Modal.getOrCreateInstance(activityModal).hide();
        show("Activity saved offline. It will be created in the online gradebook during synchronization.", "warning");
        await render();
    }

    async function save(input) {
        const itemId = Number(input.dataset.itemId);
        const studentId = Number(input.dataset.studentId);
        const maximum = Number(input.max);
        const raw = input.value.trim();
        let score = null;
        if (raw !== "") {
            score = Number(raw);
            if (!Number.isFinite(score) || score < 0 || score > maximum) {
                input.classList.add("is-invalid");
                show(`Enter a score from 0 to ${maximum}.`, "danger");
                return;
            }
        }
        input.classList.remove("is-invalid");
        const id = localId(itemId, studentId);
        const old = await N1OfflineDB.get("cached_score", id) || {};
        await N1OfflineDB.put("cached_score", {...old, local_id:id, class_id:classId, term, grade_item_id:itemId, student_id:studentId, score, highest_possible_score:maximum, sync_status:"pending", sync_error:"", local_updated_at:new Date().toISOString()});
        await queueSync();
        input.classList.remove("failed"); input.classList.add("pending");
        show(navigator.onLine ? "Score saved on this device. Click Synchronize to upload it." : "Score saved offline. It will synchronize when internet returns.", "warning");
    }

    async function render() {
        if (!classId) { show("The class identifier is missing.", "danger"); return; }
        await N1OfflineDB.open();
        const cachedClass = await N1OfflineDB.get("cached_classes", classId);
        const items = (await N1OfflineDB.getAll("cached_grade_items")).filter((item) => Number(item.class_id) === classId && String(item.term) === term).sort((a,b) => a.component.localeCompare(b.component) || Number(a.position)-Number(b.position));
        const students = (await N1OfflineDB.getAll("cached_students")).filter((student) => Number(student.class_id) === classId).sort((a,b) => a.lastname.localeCompare(b.lastname) || a.firstname.localeCompare(b.firstname));
        const scores = new Map();
        for (const score of await N1OfflineDB.getAll("cached_score")) if (Number(score.class_id) === classId && String(score.term) === term) scores.set(`${score.grade_item_id}:${score.student_id}`, score);
        if (!cachedClass || !items.length || !students.length) { table.hidden = true; empty.hidden = false; show("Download this term’s gradebook while online first.", "warning"); return; }
        document.getElementById("pageTitle").textContent = `${cachedClass.class_name} — Term ${term}`;
        document.getElementById("pageDescription").textContent = `${cachedClass.subject || ""} · ${students.length} learners`;
        addButton.hidden = Boolean(cachedClass.gradebook_locked);
        head.innerHTML = `<tr><th class="student-name">Learner</th>${items.map((item) => `<th>${item.title}${item.offline_pending ? " <small>(pending)</small>" : ""}<br><small>${item.component_label || item.component} · ${item.highest_possible_score} pts</small></th>`).join("")}</tr>`;
        body.innerHTML = "";
        for (const student of students) {
            const row = document.createElement("tr");
            row.innerHTML = `<td class="student-name"><strong>${student.lastname}, ${student.firstname}</strong><div class="small text-muted">${student.lrn || ""}</div></td>${items.map((item) => { const score=scores.get(`${item.item_id}:${student.student_id}`); const cls=score?.sync_status === "pending" ? "pending" : score?.sync_status === "failed" ? "failed" : ""; return `<td><input type="number" class="form-control score-input ${cls}" min="0" max="${item.highest_possible_score}" step="0.01" value="${score?.score ?? ""}" data-item-id="${item.item_id}" data-student-id="${student.student_id}" ${cachedClass.gradebook_locked ? "disabled" : ""}></td>`; }).join("")}`;
            body.appendChild(row);
        }
        table.hidden = false; empty.hidden = true;
        body.querySelectorAll(".score-input").forEach((input) => input.addEventListener("change", () => save(input)));
        show(cachedClass.gradebook_locked ? "This class record is locked because the final report was submitted." : "Scores are saved locally as you enter them.", cachedClass.gradebook_locked ? "warning" : "info");
    }

    async function sync() {
        if (!navigator.onLine) { show("Connect to the internet before synchronizing.", "warning"); return; }
        syncButton.disabled = true;
        try { const result = await window.N1OfflineGradeSync.synchronizeNow(); await render(); show(result.failed ? `${result.failed} synchronization item(s) failed.` : result.synchronized ? "Offline scores synchronized successfully." : "There are no scores waiting to synchronize.", result.failed ? "danger" : result.synchronized ? "success" : "info"); }
        catch (error) { show(error.message || "Scores could not be synchronized.", "danger"); }
        finally { syncButton.disabled = false; }
    }
    syncButton.addEventListener("click", sync);
    addButton?.addEventListener("click", () => {
        activityError.hidden = true;
        if (window.bootstrap?.Modal) {
            bootstrap.Modal.getOrCreateInstance(activityModal).show();
        }
    });
    activityForm?.addEventListener("submit", addActivity);
    addEventListener("online", status); addEventListener("offline", status); status();
    addEventListener("n1:grade-sync", (event) => { if (Number(event.detail?.classId) === classId && String(event.detail?.term) === term) render(); });
    render().catch((error) => { console.error(error); show("The offline gradebook could not be opened.", "danger"); });
})();
