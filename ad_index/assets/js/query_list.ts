class QueryList {
    public element: HTMLDivElement
    public items: HTMLDivElement

    public onedit: (adQueryId: string) => void
    public onadd: () => void

    private loader: Loader

    constructor(private session: SessionInfo) {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'query-list')

        const addButtonContainer = document.createElement('div')
        addButtonContainer.setAttribute('class', 'query-list-add-button-container')
        const addButton = document.createElement('button')
        addButton.setAttribute('class', 'query-list-add-button')
        addButton.textContent = 'Add Query'
        addButton.addEventListener('click', () => this.onadd())
        addButtonContainer.appendChild(addButton)
        this.element.appendChild(addButtonContainer)

        this.items = document.createElement('div')
        this.items.setAttribute('class', 'query-list-items')
        this.element.appendChild(this.items)

        this.loader = new Loader()

        this.reload()
    }

    public async reload() {
        this.items.replaceChildren(this.loader.element)
        let results
        try {
            results = await getAdQueries(this.session.sessionId)
        } catch (e) {
            this.showError(e.toString())
            return
        }
        this.renderResults(results)
    }

    private showError(e: string) {
        const errorMsg = document.createElement('div')
        errorMsg.setAttribute('class', 'query-list-error-message')
        errorMsg.textContent = e
        this.items.replaceChildren(errorMsg)
        return
    }

    private renderResults(results: Array<AdQueryResult>) {
        if (results.length === 0) {
            const empty = document.createElement('div')
            empty.setAttribute('class', 'query-list-empty-message')
            empty.textContent = 'No queries have been added yet.'
            this.items.replaceChildren(empty)
            return
        }
        const elements = results.map((info) => {
            const elem = document.createElement('div')
            elem.setAttribute('class', 'query-list-item')

            const nickname = document.createElement('label')
            nickname.setAttribute('class', 'query-list-item-nickname')
            nickname.textContent = info.nickname
            elem.appendChild(nickname)

            const query = document.createElement('label')
            query.setAttribute('class', 'query-list-item-query')
            query.textContent = info.query
            elem.appendChild(query)

            const subRow = document.createElement('div')
            subRow.setAttribute('class', 'query-list-item-subscription')
            const subCheckbox = document.createElement('input')
            subCheckbox.setAttribute('type', 'checkbox')
            subCheckbox.setAttribute('class', 'query-list-item-subscription-input')
            subCheckbox.id = `${Math.random()}${Math.random()}`
            subCheckbox.checked = info.subscribed
            subRow.appendChild(subCheckbox)
            const subCheckboxLabel = document.createElement('label')
            subCheckboxLabel.setAttribute('class', 'query-list-item-subscription-label')
            subCheckboxLabel.setAttribute('for', subCheckbox.id)
            subCheckboxLabel.textContent = 'Notify me'
            subRow.appendChild(subCheckboxLabel)
            elem.appendChild(subRow)

            subCheckbox.addEventListener('input', () => {
                const checked = subCheckbox.checked
                subRow.classList.add('disabled')
                toggleAdQuerySubscription(
                    this.session.sessionId,
                    info.adQueryId,
                    checked,
                ).catch((_) => {
                    subCheckbox.checked = info.subscribed
                }).finally(() => {
                    subRow.classList.remove('disabled')
                })
            })
            subRow.addEventListener('click', (e) => e.stopPropagation())

            const actions = document.createElement('div')
            actions.setAttribute('class', 'query-list-item-actions')
            const buttons = ['Delete', 'Edit', 'View'].map((name) => {
                const button = document.createElement('button')
                button.textContent = name
                button.setAttribute('class', `query-list-item-actions-${name.toLowerCase()}`)
                actions.appendChild(button)
                return button
            })
            buttons[1].addEventListener('click', () => this.onedit(info.adQueryId))
            elem.appendChild(actions)

            return elem
        })
        this.items.replaceChildren(...elements)
    }
}
