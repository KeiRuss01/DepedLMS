(() => {
    "use strict";
    const connection = document.getElementById("connectionStatus");
    const onlineLink = document.getElementById("onlineSystemLink");

    function safe(value) {
        return String(value ?? "").replace(/[&<>"']/g, (character) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        })[character]);
    }

    function belongsToCurrentUser(record, identity) {
        return Boolean(
            record &&
            identity?.user_id &&
            record.user_id &&
            Number(record.user_id) === Number(identity.user_id)
        );
    }

    function updateConnection() {
        const online = navigator.onLine;
        connection.textContent = online ? "Online" : "Offline";
        connection.classList.toggle("online", online);
        onlineLink.hidden = !online;
    }

    function updateOnlineDestination(identity) {
        const role = String(identity?.account_role || "").toLowerCase();
        const destinations = {
            supervisor: "/administration/dashboard/",
            principal: "/administration/principal/dashboard/",
            teacher: "/classroom/",
            student: "/classroom/",
            parent: "/classroom/",
        };

        onlineLink.href = destinations[role] || "/accounts/home/";
    }

    function moduleCard(module) {
        const article = document.createElement("article");
        article.className = "class-card";
        article.innerHTML = `<div class="small text-primary mb-2">Term ${safe(module.term)}${module.week ? ` · ${safe(module.week)}` : ""}</div><h3>${safe(module.title || "Downloaded module")}</h3><p class="text-muted small">${safe(module.class_name)}</p><div class="d-flex flex-wrap gap-2"><a class="btn btn-sm btn-primary" href="/offline/modules/?module=${encodeURIComponent(module.id)}">View offline</a><a class="btn btn-sm btn-outline-primary" href="/offline/modules/editor/?module=${encodeURIComponent(module.id)}">Answer offline</a></div>`;
        return article;
    }

    function classCard(item) {
        const article = document.createElement("article");
        article.className = "class-card";
        const term = String(item.term || item.quarter || "1").replace(/[^123]/g, "") || "1";
        article.innerHTML = `<h3>${safe(item.class_name || "Saved class")}</h3><p class="text-muted small">${safe([item.subject,item.grade_level,item.section].filter(Boolean).join(" · "))}</p><div class="d-flex flex-wrap gap-2"><a class="btn btn-sm btn-outline-primary" href="/offline/attendance/?class=${encodeURIComponent(item.id)}"><i class="bi bi-calendar-check"></i> Attendance</a><a class="btn btn-sm btn-outline-primary" href="/offline/grades/?class=${encodeURIComponent(item.id)}&term=${term}"><i class="bi bi-journal-check"></i> Grades</a></div>`;
        return article;
    }

    async function load() {
        await window.N1OfflineDB.open();
        const [modules, queue, drafts, classes, identity] = await Promise.all([
            N1OfflineDB.getAll("cached_modules"), N1OfflineDB.getAll("offline_queue"),
            N1OfflineDB.getAll("draft_submissions"), N1OfflineDB.getAll("cached_classes"),
            N1OfflineDB.get("device_identity", "current"),
        ]);
        const greeting = document.getElementById("accountGreeting");
        if (identity?.account_name) {
            greeting.textContent = `Welcome, ${identity.account_name}`;
            if (identity.account_role_label) greeting.textContent += ` · ${identity.account_role_label}`;
            greeting.hidden = false;
        }
        const accountRole = String(
            identity?.account_role || ""
        ).toLowerCase();
        updateOnlineDestination(identity);
        const isStudent = accountRole === "student";
        const isTeacher = accountRole === "teacher";
        const accountModules = isStudent
            ? modules.filter((item) =>
                belongsToCurrentUser(item, identity))
            : [];
        const accountDrafts = isStudent
            ? drafts.filter((item) =>
                belongsToCurrentUser(item, identity))
            : [];
        const teacherClasses = isTeacher
            ? classes.filter((item) => (
                item.teacher_user_id &&
                Number(item.teacher_user_id) === Number(identity.user_id)
            ))
            : [];
        const teacherClassIds = new Set(
            teacherClasses.map((item) => Number(item.id))
        );
        const accountQueue = isStudent
            ? queue.filter((item) =>
                belongsToCurrentUser(item, identity))
            : isTeacher
                ? queue.filter((item) =>
                    teacherClassIds.has(Number(item.class_id)))
                : [];

        document.getElementById("moduleCount").textContent =
            accountModules.length;
        document.getElementById("pendingCount").textContent =
            accountQueue.filter((item) =>
                ["pending", "failed", "syncing"].includes(item.status)
            ).length;
        document.getElementById("draftCount").textContent =
            accountDrafts.length;
        document.getElementById("moduleSummaryCard").hidden =
            !isStudent;
        document.getElementById("draftSummaryCard").hidden =
            !isStudent;
        document.getElementById("studentModuleSection").hidden =
            !isStudent;
        const recent = document.getElementById("recentModules");
        recent.replaceChildren(...accountModules.slice().sort((a,b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))).slice(0, 4).map(moduleCard));
        document.getElementById("noModules").hidden =
            !isStudent || accountModules.length > 0;
        document.getElementById("teacherSection").hidden = teacherClasses.length === 0;
        document.getElementById("offlineClasses").replaceChildren(...teacherClasses.map(classCard));
    }

    addEventListener("online", updateConnection);
    addEventListener("offline", updateConnection);
    onlineLink.addEventListener("click", (event) => {
        if (!navigator.onLine) {
            event.preventDefault();
            return;
        }

        event.preventDefault();
        window.location.assign(onlineLink.href);
    });
    updateConnection();
    load().catch((error) => {
        console.error("Offline home could not load:", error);
        document.getElementById("noModules").hidden = false;
    });
})();
