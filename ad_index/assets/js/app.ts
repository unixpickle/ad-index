interface Window {
    app: App;
}

class App {
    registration: ServiceWorkerRegistration;
    session: SessionInfo;
    queryList: QueryList;
    notificationsButton: HTMLButtonElement;

    constructor(session: SessionInfo) {
        this.registration = null;
        this.session = session;

        this.queryList = new QueryList(this.session);
        document.body.appendChild(this.queryList.element);

        this.notificationsButton = (
            document.getElementById('notifications-button') as HTMLButtonElement
        );
        this.notificationsButton.addEventListener('click', () => this.toggleNotifications());

        navigator.serviceWorker.register('/js/worker.js').then((reg) => {
            this.registration = reg;
            // TODO: use active state to update button.
        }).catch((e) => {
            // TODO: handle error here.
        });
    }

    async toggleNotifications() {
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
        // TODO: update toggle UI
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
