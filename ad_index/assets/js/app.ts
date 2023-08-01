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
            const sub = await this.registration.pushManager.subscribe({ userVisibleOnly: true });
            console.log('got sub', sub);
            console.log(sub.toJSON());
        } catch (e) {
            console.log('error', e);
        }
    }
}

window.addEventListener('load', () => {
    window.app = new App();
});
