interface Window {
    app: App;
}

class App {
    registration: ServiceWorkerRegistration;
    notificationsButton: HTMLButtonElement;
    session: SessionInfo;

    constructor(session: SessionInfo) {
        this.registration = null;
        this.notificationsButton = (
            document.getElementById('notifications-button') as HTMLButtonElement
        );
        this.notificationsButton.addEventListener('click', () => this.toggleNotifications());

        this.session = session;

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
            const sub = await this.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.session.vapidPub,
            });
            await this._syncWebPushSubscription(sub);
        } catch (e) {
            console.log('error toggling notifications:', e);
            await this._syncWebPushSubscription(null);
        }
    }

    async _syncWebPushSubscription(sub: PushSubscription) {
        sub = sub || await this.registration.pushManager.getSubscription();
        await updatePushSub(
            this.session.sessionId,
            sub ? JSON.stringify(sub.toJSON()) : null,
        );
    }
}

window.addEventListener('load', () => {
    if (localStorage.getItem('sessionId')) {
        const session = {
            sessionId: localStorage.getItem('sessionId'),
            vapidPub: localStorage.getItem('vapidPub'),
        }
        window.app = new App(session);
    } else {
        createSession().then((session) => {
            window.app = new App(session);
        }).catch((e) => {
            // TODO: handle this global error here.
            console.log('Error creating session: ' + e);
            alert('Failed to create session. Please refresh.');
        });
    }

});
