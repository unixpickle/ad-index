interface Window {
    app: App;
}

class App {
    registration: ServiceWorkerRegistration;
    notificationsButton: HTMLButtonElement;

    constructor() {
        this.registration = null;
        this.notificationsButton = (
            document.getElementById('notifications-button') as HTMLButtonElement
        );
        this.notificationsButton.addEventListener('click', () => this.toggleNotifications());

        navigator.serviceWorker.register('/js/worker.js').then((reg) => {
            this.registration = reg;
        }).catch((e) => {
            this.showWorkerError(e.toString());
        });
    }

    showWorkerError(e: string) {
        console.log('error registering worker: ' + e);
        // TODO: this.
    }

    async toggleNotifications() {
        console.log('attempting to subscribe to notifications');
        try {
            let vapidPub = localStorage.getItem('vapidPub');
            if (!vapidPub) {
                const session = await createSession();
                localStorage.setItem('vapidPub', session.vapidPub);
                localStorage.setItem('sessionId', session.sessionId);
                vapidPub = session.vapidPub;
            }
            const sub = await this.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: vapidPub,
            });
            console.log('got subscription:', sub);
            await updatePushSub(
                localStorage.getItem('sessionId'),
                sub ? JSON.stringify(sub.toJSON()) : null,
            );
        } catch (e) {
            console.log('error', e);
        }
    }
}

window.addEventListener('load', () => {
    window.app = new App();
});
