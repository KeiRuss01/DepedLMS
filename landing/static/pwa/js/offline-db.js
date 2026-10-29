(() => {
    "use strict";

    const DB_NAME = "n1_hlms_offline";
    const DB_VERSION = 4;

    let databasePromise = null;

    function createStore(database, name, options, indexes = []) {
        if (database.objectStoreNames.contains(name)) {
            return;
        }

        const store = database.createObjectStore(name, options);

        indexes.forEach((index) => {
            store.createIndex(
                index.name,
                index.keyPath,
                index.options || {}
            );
        });
    }

    function openDatabase() {
        if (databasePromise) {
            return databasePromise;
        }

        databasePromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            let settled = false;

            const failOpen = (error) => {
                if (settled) return;
                settled = true;
                databasePromise = null;
                reject(error);
            };

            request.onupgradeneeded = (event) => {
                const database = event.target.result;

                createStore(
                    database,
                    "cached_modules",
                    { keyPath: "id" },
                    [
                        { name: "class_id", keyPath: "class_id" },
                        { name: "updated_at", keyPath: "updated_at" }
                    ]
                );

                createStore(
                    database,
                    "draft_submissions",
                    { keyPath: "local_id" },
                    [
                        { name: "module_id", keyPath: "module_id" },
                        { name: "student_id", keyPath: "student_id" },
                        { name: "status", keyPath: "status" }
                    ]
                );

                createStore(
                    database,
                    "offline_queue",
                    {
                        keyPath: "queue_id",
                        autoIncrement: true
                    },
                    [
                        { name: "action_type", keyPath: "action_type" },
                        { name: "status", keyPath: "status" },
                        { name: "created_at", keyPath: "created_at" }
                    ]
                );

                createStore(
                    database,
                    "sync_metadata",
                    { keyPath: "key" }
                );

                createStore(
                    database,
                    "device_identity",
                    { keyPath: "key" }
                );

                createStore(
                    database,
                    "cached_attendance",
                    { keyPath: "local_id" },
                    [
                        { name: "class_id", keyPath: "class_id" },
                        { name: "student_id", keyPath: "student_id" },
                        { name: "attendance_date", keyPath: "attendance_date" },
                        { name: "sync_status", keyPath: "sync_status" }
                    ]
                );

                createStore(
                    database,
                    "cached_score",
                    { keyPath: "local_id" },
                    [
                        { name: "class_id", keyPath: "class_id" },
                        { name: "student_id", keyPath: "student_id" },
                        { name: "module_id", keyPath: "module_id" },
                        { name: "sync_status", keyPath: "sync_status" }
                    ]
                );

                createStore(
                    database,
                    "cached_grade_items",
                    { keyPath: "local_id" },
                    [
                        {
                            name: "class_id",
                            keyPath: "class_id",
                        },
                        {
                            name: "term",
                            keyPath: "term",
                        },
                        {
                            name: "component",
                            keyPath: "component",
                        },
                    ]
                );

                createStore(
                    database,
                    "cached_classes",
                    { keyPath: "id" },
                    [
                        {
                            name: "teacher_id",
                            keyPath: "teacher_id",
                        },
                        {
                            name: "updated_at",
                            keyPath: "updated_at",
                        },
                    ]
                );

                createStore(
                    database,
                    "cached_students",
                    { keyPath: "local_id" },
                    [
                        {
                            name: "class_id",
                            keyPath: "class_id",
                        },
                        {
                            name: "student_id",
                            keyPath: "student_id",
                        },
                        {
                            name: "lastname",
                            keyPath: "lastname",
                        },
                    ]
                );
            };

            request.onsuccess = () => {
                if (settled) {
                    request.result.close();
                    return;
                }

                settled = true;
                request.result.onversionchange = () => {
                    request.result.close();
                    databasePromise = null;
                };
                resolve(request.result);
            };

            request.onerror = () => {
                failOpen(request.error);
            };

            request.onblocked = () => {
                console.warn(
                    "IndexedDB update is blocked. Close other open HLMS tabs."
                );
                failOpen(new Error(
                    "Offline storage update is blocked. Close other HLMS " +
                    "tabs, reload this page, then try again."
                ));
            };
        });

        return databasePromise;
    }

    function requestResult(request) {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    function transactionFinished(transaction) {
        return new Promise((resolve, reject) => {
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
            transaction.onabort = () => reject(transaction.error);
        });
    }

    async function put(storeName, value) {
        const database = await openDatabase();
        const transaction = database.transaction(storeName, "readwrite");
        const finished = transactionFinished(transaction);
        const request = transaction.objectStore(storeName).put(value);

        const key = await requestResult(request);
        await finished;

        return key;
    }

    async function get(storeName, key) {
        const database = await openDatabase();
        const transaction = database.transaction(storeName, "readonly");

        return requestResult(
            transaction.objectStore(storeName).get(key)
        );
    }

    async function getAll(storeName) {
        const database = await openDatabase();
        const transaction = database.transaction(storeName, "readonly");

        return requestResult(
            transaction.objectStore(storeName).getAll()
        );
    }

    async function remove(storeName, key) {
        const database = await openDatabase();
        const transaction = database.transaction(storeName, "readwrite");
        const finished = transactionFinished(transaction);

        transaction.objectStore(storeName).delete(key);
        await finished;
    }

    async function clear(storeName) {
        const database = await openDatabase();
        const transaction = database.transaction(storeName, "readwrite");
        const finished = transactionFinished(transaction);

        transaction.objectStore(storeName).clear();
        await finished;
    }

    window.N1OfflineDB = {
        open: openDatabase,
        put,
        get,
        getAll,
        remove,
        clear
    };
})();
