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
            await fetch(`/api/update_push_sub?session_id=${encodeURIComponent(localStorage.getItem('sessionId'))}&push_sub=${JSON.stringify(sub.toJSON())}`);
        } catch (e) {
            console.log('error', e);
        }
    }
}

interface APIResponse<T> {
    data: T
    error: string
}

interface SessionInfo {
    sessionId: string
    vapidPub: string
}

class ServerError extends Error {
}

async function createSession(): Promise<SessionInfo> {
    return extractSuccess(await (await fetch('/api/create_session')).json());
}

function extractSuccess<T>(obj: any): T {
    const resp = obj as APIResponse<T>;
    if (resp.error) {
        throw new ServerError(resp.error);
    } else {
        return resp.data;
    }
}

window.addEventListener('load', () => {
    window.app = new App();
});
