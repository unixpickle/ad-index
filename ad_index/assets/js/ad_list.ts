class AdList {
    public element: HTMLDivElement
    private status: HTMLDivElement
    private statusNextPull: StatusField
    private statusLastPull: StatusField
    private statusLastNotify: StatusField
    private statusLastError: StatusField
    private clearField: HTMLDivElement
    private clearButtonContainer: HTMLTableCellElement
    private clearButton: HTMLButtonElement
    private items: HTMLDivElement
    private loader: Loader

    constructor(private session: SessionInfo, private adQueryId: string) {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'ad-list')

        this.status = document.createElement('div')
        this.status.setAttribute('class', 'ad-list-status')
        this.statusNextPull = new StatusField('Next pull', '-')
        this.statusLastPull = new StatusField('Last pull', '-')
        this.statusLastNotify = new StatusField('Last notify', '-')
        this.statusLastError = new StatusField('Last error', '-')
        this.status.appendChild(this.statusNextPull.element)
        this.status.appendChild(this.statusLastPull.element)
        this.status.appendChild(this.statusLastNotify.element)
        this.status.appendChild(this.statusLastError.element)
        this.clearField = document.createElement('div')
        this.clearField.setAttribute('class', 'ad-list-status-clear-field')
        this.clearButtonContainer = document.createElement('td')
        this.clearButtonContainer.setAttribute('colspan', '2')
        this.clearButton = document.createElement('button')
        this.clearButton.textContent = 'Clear'
        this.clearButton.addEventListener('click', () => this.clear())
        this.clearButtonContainer.appendChild(this.clearButton)
        this.clearField.appendChild(this.clearButtonContainer)
        this.status.appendChild(this.clearField)

        this.items = document.createElement('div')
        this.items.setAttribute('class', 'ad-list-items')

        this.loader = new Loader()
        this.items.appendChild(this.loader.element)

        this.reload()
    }

    public async reload() {
        let status: AdQueryStatus
        try {
            status = await getAdQueryStatus(this.session.sessionId, this.adQueryId)
        } catch (e) {
            this.showError(e.toString())
            return
        }
        this.statusNextPull.update(status.nextPull)
        this.statusLastPull.update(status.lastPull)
        this.statusLastNotify.update(status.lastNotify)
        this.statusLastError.update(status.lastError)
        this.element.appendChild(this.status)

        let content: AdContent[]
        try {
            content = await listAdContent(this.adQueryId)
        } catch (e) {
            this.showError(e.toString())
            return
        }
        this.element.appendChild(this.items)
        this.showList(content)
    }

    public async clear() {
        this.items.replaceChildren(this.loader.element)
        this.element.replaceChildren(this.items)
        try {
            await clearAdQuery(this.adQueryId)
        } catch (e) {
            this.showError(e.toString())
            return
        }
        await this.reload()
    }

    private showError(e: string) {
        const errorMsg = document.createElement('div')
        errorMsg.setAttribute('class', 'ad-list-error-message')
        errorMsg.textContent = e
        this.element.replaceChildren(this.items)
        this.items.replaceChildren(errorMsg)
        return
    }

    private showList(items: AdContent[]) {
        if (items.length == 0) {
            const empty = document.createElement('div')
            empty.setAttribute('class', 'ad-list-empty-message')
            empty.textContent = 'No ads have been found yet.'
            this.items.replaceChildren(empty)
            return
        }
        const elements = items.map((item) => {
            const element = document.createElement('div')
            element.setAttribute('class', 'ad-list-item')

            const advertiser = document.createElement('a')
            advertiser.textContent = item.accountName
            advertiser.setAttribute('href', item.accountUrl)
            advertiser.setAttribute('class', 'ad-list-item-name')
            element.appendChild(advertiser)

            const link = document.createElement('a')
            link.setAttribute('class', 'ad-list-item-view-link')
            link.setAttribute('href', `https://www.facebook.com/ads/library/?id=${item.id}`)
            link.setAttribute('target', '_blank')

            const screenshot = document.createElement('img')
            screenshot.setAttribute('class', 'ad-list-item-screenshot')
            screenshot.setAttribute(
                'src',
                (
                    `/screenshot?ad_query_id=${encodeURIComponent(this.adQueryId)}` +
                    `&id=${encodeURIComponent(item.id)}`
                )
            )
            link.appendChild(screenshot)
            element.appendChild(link)

            const text = document.createElement('div')
            text.setAttribute('class', 'ad-list-item-text')
            text.textContent = item.text
            element.appendChild(text)

            return element
        })
        this.items.replaceChildren(...elements)
    }
}

class StatusField {
    public element: HTMLDivElement
    private nameLabel: HTMLLabelElement
    private contents: HTMLLabelElement

    constructor(name: string, initContents: string) {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'ad-list-status-item')
        this.nameLabel = document.createElement('label')
        this.nameLabel.setAttribute('class', 'ad-list-status-item-name')
        this.nameLabel.textContent = name
        this.contents = document.createElement('label')
        this.contents.setAttribute('class', 'ad-list-status-item-contents')
        this.contents.textContent = initContents
        this.element.appendChild(this.nameLabel)
        this.element.appendChild(this.contents)
    }

    update(data: string | number) {
        if (data == null) {
            this.contents.textContent = '-'
            this.contents.classList.add('ad-list-status-item-contents-empty')
            return
        }
        this.contents.classList.remove('ad-list-status-item-contents-empty')
        if (typeof data == 'string') {
            this.contents.textContent = data as string
        } else {
            const date = new Date(data * 1000)
            this.contents.textContent = date.toLocaleString()
        }
    }
}
