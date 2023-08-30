class AdList {
    public element: HTMLDivElement
    public items: HTMLDivElement

    private loader: Loader

    constructor(private session: SessionInfo, private adQueryId: string) {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'ad-list')

        this.items = document.createElement('div')
        this.items.setAttribute('class', 'ad-list-items')
        this.element.appendChild(this.items)

        this.loader = new Loader()
        this.items.appendChild(this.loader.element)

        this.reload()
    }

    public async reload() {
        let content: AdContent[]
        try {
            content = await listAdContent(this.adQueryId)
        } catch (e) {
            this.showError(e.toString())
            return
        }
        this.showList(content)
    }

    private showError(e: string) {
        const errorMsg = document.createElement('div')
        errorMsg.setAttribute('class', 'ad-list-error-message')
        errorMsg.textContent = e
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

            const text = document.createElement('div')
            text.setAttribute('class', 'ad-list-item-text')
            text.textContent = item.text
            element.appendChild(text)

            return element
        })
        this.items.replaceChildren(...elements)
    }
}
