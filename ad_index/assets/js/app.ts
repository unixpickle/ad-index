interface Window {
    app: App
}

type OnNav = (state: ViewState) => void

abstract class ViewState {
    constructor(public onnavigate: OnNav, protected session: SessionInfo) {
    }

    abstract get path(): string
    abstract get element(): HTMLElement

    swapFrom(state: ViewState): void {
        const oldElem = state.element
        oldElem.parentElement.replaceChild(this.element, oldElem)
    }
}

class QueryListViewState extends ViewState {
    private queryList: QueryList

    constructor(onnavigate: OnNav, session: SessionInfo) {
        super(onnavigate, session)
        this.queryList = new QueryList(session)
        this.queryList.onedit = (adQueryId) => {
            this.onnavigate(new QueryEditorViewState(onnavigate, session, adQueryId, this))
        }
        this.queryList.onadd = () => {
            this.onnavigate(new QueryEditorViewState(onnavigate, session, null, this))
        }
    }

    get path(): string {
        return ''
    }

    get element(): HTMLElement {
        return this.queryList.element
    }
}

class QueryEditorViewState extends ViewState {
    private editor: QueryEditor

    constructor(
        onnavigate: OnNav,
        session: SessionInfo,
        private adQueryId?: string,
        private previous?: ViewState,
    ) {
        super(onnavigate, session)
        this.editor = new QueryEditor(session, adQueryId)

        this.editor.oncancel = () => {
            // Go to the previous view if possible.
            if (this.previous) {
                this.onnavigate(this.previous)
            } else {
                this.editor.oncomplete()
            }
        }
        this.editor.oncomplete = () => {
            this.onnavigate(new QueryListViewState(this.onnavigate, this.session))
        }
    }

    get path(): string {
        if (this.adQueryId) {
            return `edit/${this.adQueryId}`
        } else {
            return `add`
        }
    }

    get element(): HTMLElement {
        return this.editor.element
    }

    swapFrom(state: ViewState): void {
        super.swapFrom(state)
    }
}

function viewStateFromPath(onnavigate: OnNav, session: SessionInfo, path: string): ViewState {
    if (path == 'add') {
        return new QueryEditorViewState(onnavigate, session)
    } else if (path.startsWith('edit/')) {
        return new QueryEditorViewState(onnavigate, session, path.substring(5))
    } else {
        return new QueryListViewState(onnavigate, session)
    }
}

class App {
    private registration: ServiceWorkerRegistration
    private navbar: Navbar
    private viewState: ViewState

    constructor(private session: SessionInfo) {
        this.registration = null

        this.navbar = new Navbar()
        document.body.appendChild(this.navbar.element)
        this.navbar.ontogglenotifications = (enabled) => this.toggleNotifications(enabled)

        const onNav = (view: ViewState) => this.navigateTo(view)
        this.viewState = viewStateFromPath(onNav, this.session, location.hash ? location.hash.substring(1) : '')
        document.body.appendChild(this.viewState.element)
        window.addEventListener('popstate', (_) => {
            const view = viewStateFromPath(onNav, this.session, location.hash ? location.hash.substring(1) : '')
            view.swapFrom(this.viewState)
            this.viewState = view
        })

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

    navigateTo(view: ViewState) {
        view.swapFrom(this.viewState)
        this.viewState = view
        history.pushState(null, '', '#' + view.path)
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
}

window.addEventListener('load', async () => {
    const loader = new Loader()
    document.body.appendChild(loader.element)
    let session
    try {
        if (localStorage.getItem('sessionId')) {
            session = {
                sessionId: localStorage.getItem('sessionId'),
                vapidPub: localStorage.getItem('vapidPub'),
            }
        } else {
            session = await createSession()
        }
    } catch (e) {
        document.body.removeChild(loader.element)
        const globalError = document.createElement('div')
        globalError.setAttribute('class', 'global-error')
        const errorHeader = document.createElement('h1')
        errorHeader.setAttribute('class', 'global-error-header')
        errorHeader.textContent = 'Error loading page'
        globalError.appendChild(errorHeader)
        const errorBody = document.createElement('div')
        errorBody.setAttribute('class', 'global-error-body')
        errorBody.textContent = e.toString()
        globalError.appendChild(errorBody)
        document.body.appendChild(globalError)
        return
    }
    document.body.removeChild(loader.element)
    window.app = new App(session)
})
