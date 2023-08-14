class Navbar {
    public element: HTMLElement
    public ontogglenotifications: (enabled: boolean) => void

    private notificationsField: HTMLDivElement
    private notificationsCheck: HTMLInputElement

    constructor() {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'navbar')

        this.notificationsField = document.createElement('div')
        this.notificationsField.setAttribute('class', 'navbar-notifications')
        this.notificationsCheck = document.createElement('input')
        this.notificationsCheck.setAttribute('type', 'checkbox')
        this.notificationsCheck.id = 'notifications-checkbox'
        this.notificationsCheck.setAttribute('class', 'navbar-notifications-check')
        const notificationsLabel = document.createElement('label')
        notificationsLabel.setAttribute('class', 'navbar-notifications-label')
        notificationsLabel.setAttribute('for', this.notificationsCheck.id)
        notificationsLabel.innerText = 'Notifications'
        this.notificationsField.appendChild(this.notificationsCheck)
        this.notificationsField.appendChild(notificationsLabel)
        this.notificationsField.classList.add('disabled')

        this.notificationsCheck.addEventListener('input', () => {
            this.notificationsField.classList.add('disabled')
            this.ontogglenotifications(this.notificationsCheck.checked)
        })

        this.element.appendChild(this.notificationsField)
    }

    public setNotificationsEnabled(enabled: boolean, available: boolean) {
        if (!available) {
            this.notificationsField.classList.add('disabled')
        } else {
            this.notificationsField.classList.remove('disabled')
        }
        this.notificationsCheck.checked = enabled
    }
}