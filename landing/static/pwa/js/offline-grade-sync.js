(() => {
    "use strict";
    let running = null;

    function cookie(name) {
        const prefix = `${name}=`;
        const found = document.cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith(prefix));
        return found ? decodeURIComponent(found.slice(prefix.length)) : "";
    }

    async function device() {
        if (window.N1DeviceRegistry) await window.N1DeviceRegistry.register();
        const identity = await N1OfflineDB.get("device_identity", "current");
        if (!identity?.device_id) throw new Error("This device has not been registered.");
        return identity;
    }

    async function scoresFor(classId, term) {
        return (await N1OfflineDB.getAll("cached_score")).filter((score) => Number(score.class_id) === Number(classId) && String(score.term) === String(term) && ["pending", "failed"].includes(score.sync_status));
    }

    async function mark(records, status, extra = {}) {
        for (const record of records) await N1OfflineDB.put("cached_score", {...record, ...extra, sync_status:status, local_updated_at:new Date().toISOString()});
    }

    async function syncItem(queueItem) {
        const classId = Number(queueItem.class_id);
        const term = String(queueItem.term);
        const cachedClass = await N1OfflineDB.get("cached_classes", classId);
        if (!cachedClass?.grade_sync_url) throw new Error("Download the gradebook again before synchronizing.");
        const records = await scoresFor(classId, term);
        if (!records.length) { await N1OfflineDB.remove("offline_queue", queueItem.queue_id); return; }
        const identity = await device();
        await mark(records, "syncing", {sync_error:""});
        const response = await fetch(cachedClass.grade_sync_url, {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json", "X-CSRFToken":cookie("csrftoken"), "X-Requested-With":"XMLHttpRequest"}, body:JSON.stringify({device_id:identity.device_id, term, records:records.map((record) => ({item_id:record.grade_item_id, student_id:record.student_id, score:record.score, client_updated_at:record.local_updated_at, base_server_updated_at:record.server_updated_at}))})});
        const data = (response.headers.get("Content-Type") || "").includes("application/json") ? await response.json() : null;
        if (!response.ok) throw new Error(data?.error || `Score synchronization failed (${response.status}).`);
        const results = new Map((data.records || []).map((record) => [`${record.item_id}:${record.student_id}`, record]));
        for (const record of records) {
            const result = results.get(`${record.grade_item_id}:${record.student_id}`);
            await N1OfflineDB.put("cached_score", {...record, score:result?.score == null ? null : Number(result.score), sync_status:"synced", sync_error:"", server_updated_at:result?.server_updated_at || null, local_updated_at:new Date().toISOString()});
        }
        await N1OfflineDB.remove("offline_queue", queueItem.queue_id);
        await N1OfflineDB.put("sync_metadata", {key:`gradebook:${classId}:${term}`, class_id:classId, term, last_pushed_at:new Date().toISOString(), server_updated_at:data.server_updated_at});
        dispatchEvent(new CustomEvent("n1:grade-sync", {detail:{status:"completed", classId, term}}));
    }

    async function syncCreatedItem(queueItem) {
        const cachedClass = await N1OfflineDB.get("cached_classes", Number(queueItem.class_id));
        if (!cachedClass?.grade_item_create_url) throw new Error("Download the gradebook again before synchronizing new activities.");
        const identity = await device();
        const response = await fetch(cachedClass.grade_item_create_url, {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json", "X-CSRFToken":cookie("csrftoken"), "X-Requested-With":"XMLHttpRequest"}, body:JSON.stringify({...queueItem.payload, device_id:identity.device_id})});
        const data = (response.headers.get("Content-Type") || "").includes("application/json") ? await response.json() : null;
        if (!response.ok) throw new Error(data?.error || `Activity synchronization failed (${response.status}).`);
        const oldItem = (await N1OfflineDB.getAll("cached_grade_items")).find((item) => Number(item.item_id) === Number(queueItem.temp_item_id) && Number(item.class_id) === Number(queueItem.class_id));
        if (oldItem) {
            await N1OfflineDB.put("cached_grade_items", {...oldItem, ...data, item_id:Number(data.item_id), offline_pending:false, updated_at:new Date().toISOString()});
        }
        for (const score of await N1OfflineDB.getAll("cached_score")) {
            if (Number(score.grade_item_id) === Number(queueItem.temp_item_id)) {
                await N1OfflineDB.put("cached_score", {...score, grade_item_id:Number(data.item_id), module_id:null});
            }
        }
        await N1OfflineDB.remove("offline_queue", queueItem.queue_id);
    }

    async function fail(queueItem, error) {
        const records = await scoresFor(queueItem.class_id, queueItem.term);
        const message = error.message || "Score synchronization failed.";
        await mark(records, "failed", {sync_error:message});
        await N1OfflineDB.put("offline_queue", {...queueItem, status:"failed", retry_count:Number(queueItem.retry_count || 0) + 1, error_message:message, updated_at:new Date().toISOString()});
        dispatchEvent(new CustomEvent("n1:grade-sync", {detail:{status:"failed", classId:Number(queueItem.class_id), term:String(queueItem.term), message}}));
    }

    async function run() {
        if (!navigator.onLine || !window.N1OfflineDB) return {synchronized:0, failed:0};
        await N1OfflineDB.open();
        const allQueue = await N1OfflineDB.getAll("offline_queue");
        const createQueue = allQueue.filter((item) => item.action_type === "grade_item_create" && ["pending", "failed"].includes(item.status));
        const scoreQueue = allQueue.filter((item) => item.action_type === "score_sync" && ["pending", "failed"].includes(item.status));
        let synchronized = 0; let failed = 0;
        for (const item of createQueue) { try { await syncCreatedItem(item); synchronized += 1; } catch (error) { console.error("Activity synchronization failed:", error); await N1OfflineDB.put("offline_queue", {...item, status:"failed", retry_count:Number(item.retry_count || 0) + 1, error_message:error.message || "Activity synchronization failed.", updated_at:new Date().toISOString()}); failed += 1; } }
        for (const item of scoreQueue) { try { await syncItem(item); synchronized += 1; } catch (error) { console.error("Score synchronization failed:", error); await fail(item, error); failed += 1; } }
        return {synchronized, failed};
    }

    function synchronizeNow() { if (!running) running = run().finally(() => { running = null; }); return running; }
    window.N1OfflineGradeSync = {synchronizeNow};
    addEventListener("online", synchronizeNow);
})();
