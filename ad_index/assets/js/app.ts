interface Window {
    app: App
}

class App {
    private registration: ServiceWorkerRegistration
    private navbar: Navbar
    private queryList: QueryList

    constructor(private session: SessionInfo) {
        this.registration = null

        this.navbar = new Navbar()
        document.body.appendChild(this.navbar.element)
        this.navbar.ontogglenotifications = (enabled) => this.toggleNotifications(enabled)

        this.queryList = new QueryList(this.session)
        document.body.appendChild(this.queryList.element)
        this.queryList.onselect = (adQueryId) => this.showQueryEditor(adQueryId)

        navigator.serviceWorker.register('/js/worker.js').then((reg) => {
            this.registration = reg
            return reg.pushManager.getSubscription()
        }).then((sub) => {
            this.navbar.setNotificationsEnabled(!!sub, true)

            // This step is not strictly necessary, but it is possible that we
            // updated our subscription and couldn't contact the server, or that
            // the user manually unsubscribed to notifications.
            return this.syncWebPushSubscription(sub)
        }).catch((e) => {
            this.showError('error setting up and syncing service worker: ' + e)
        })
    }

    showError(e: string) {
        alert(e)
    }

    private async toggleNotifications(enabled: boolean) {
        let currentSub
        try {
            currentSub = await this.registration.pushManager.getSubscription()
        } catch (e) {
            this.showError('error getting current push subscription: ' + e)
            return
        }
        if (!enabled && currentSub) {
            try {
                await currentSub.unsubscribe()
            } catch (e) {
                this.navbar.setNotificationsEnabled(true, true)
                this.showError('error unsubscribing: ' + e)
                return
            }
            currentSub = null
        } else if (enabled) {
            try {
                currentSub = await this.registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: this.session.vapidPub,
                })
            } catch (e) {
                this.navbar.setNotificationsEnabled(false, true)
                this.showError('error subscribing to push notifications: ' + e)
                return
            }
        }
        try {
            await this.syncWebPushSubscription(currentSub)
            this.navbar.setNotificationsEnabled(enabled, true)
        } catch (e) {
            this.navbar.setNotificationsEnabled(enabled, false)
            this.showError('error contacting server (please try refreshing the page): ' + e)
        }
    }

    private async syncWebPushSubscription(sub: PushSubscription) {
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
