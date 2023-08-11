interface Window {
    app: App
}

class App {
    private registration: ServiceWorkerRegistration
    private queryList: QueryList
    private notificationsButton: HTMLButtonElement

    constructor(private session: SessionInfo) {
        this.registration = null

        this.queryList = new QueryList(this.session)
        document.body.appendChild(this.queryList.element)
        this.queryList.onselect = (adQueryId) => this.showQueryEditor(adQueryId)

        this.notificationsButton = (
            document.getElementById('notifications-button') as HTMLButtonElement
        )
        this.notificationsButton.addEventListener('click', () => this.toggleNotifications())

        navigator.serviceWorker.register('/js/worker.js').then((reg) => {
            this.registration = reg
            // TODO: use active state to update button.
        }).catch((e) => {
            // TODO: handle error here.
        })
    }

    private async toggleNotifications() {
        try {
            const sub = await this.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.session.vapidPub,
            })
            await this.syncWebPushSubscription(sub)
        } catch (e) {
            console.log('error toggling notifications:', e)
            await this.syncWebPushSubscription()
        }
        // TODO: update toggle UI
    }

    private async syncWebPushSubscription(sub?: PushSubscription) {
        sub = sub || await this.registration.pushManager.getSubscription()
        await updatePushSub(
            this.session.sessionId,
            sub ? JSON.stringify(sub.toJSON()) : null,
        )
    }

    private showQueryEditor(adQueryId: string) {
        const editor = new QueryEditor(this.session, adQueryId)
        document.body.replaceChild(editor.element, this.queryList.element)
        editor.oncomplete = () => {
            document.body.replaceChild(this.queryList.element, editor.element)
            this.queryList.reload()
        }
    }
}

window.addEventListener('load', () => {
    if (localStorage.getItem('sessionId')) {
        const session = {
            sessionId: localStorage.getItem('sessionId'),
            vapidPub: localStorage.getItem('vapidPub'),
        }
        window.app = new App(session)
    } else {
        createSession().then((session) => {
            window.app = new App(session)
        }).catch((e) => {
            // TODO: handle this global error here.
            console.log('Error creating session: ' + e)
            alert('Failed to create session. Please refresh.')
        })
    }

})
