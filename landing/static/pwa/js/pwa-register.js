(() => {
    let deferredInstallPrompt = null;

    const getInstallButton = () => document.getElementById('installApp');
    const getInstallNote = () => document.getElementById('installNote');

    const updateInstallMessage = (message) => {
        const note = getInstallNote();
        if (note) note.textContent = message;
    };

    if ('serviceWorker' in navigator) {
        window.addEventListener('load', async () => {
            try {
                await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
            } catch (error) {
                console.error('HLMS service worker registration failed.', error);
            }
        });
    }

    window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault();
        deferredInstallPrompt = event;

        const button = getInstallButton();
        if (button) {
            button.disabled = false;
            button.hidden = false;
        }
        updateInstallMessage('This device is ready to install the HLMS app.');
    });

    document.addEventListener('click', async (event) => {
        const button = event.target.closest('#installApp');
        if (!button) return;

        if (!deferredInstallPrompt) {
            updateInstallMessage('Use your browser menu and choose Install app or Add to Home Screen.');
            return;
        }

        deferredInstallPrompt.prompt();
        const choice = await deferredInstallPrompt.userChoice;
        deferredInstallPrompt = null;

        if (choice.outcome === 'accepted') {
            updateInstallMessage('Installation started.');
        } else {
            updateInstallMessage('Installation was cancelled. You can install it later.');
        }
    });

    window.addEventListener('appinstalled', () => {
        deferredInstallPrompt = null;
        const button = getInstallButton();
        if (button) button.hidden = true;
        updateInstallMessage('HLMS is installed on this device.');
    });
})();
