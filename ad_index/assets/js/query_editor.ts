class QueryEditor {
    public element: HTMLElement
    public oncancel: () => void
    public oncomplete: () => void

    private loader: Loader
    private nickname: QueryEditorField
    private query: QueryEditorField
    private matchTerms: QueryEditorField
    private accountFilter: QueryEditorField
    private subscribed: QueryEditorField
    private actions: HTMLDivElement

    constructor(private session: SessionInfo, private adQueryId?: string) {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'query-editor')

        this.loader = new Loader()
        this.nickname = new QueryEditorField('Name', '', true, 'Example: "Nike Deals"')
        this.query = new QueryEditorField('Query', '', true, "Example: nike")
        this.matchTerms = new QueryEditorField('Match terms', '', false, "Example: discount,% off")
        this.accountFilter = new QueryEditorField('Account name', '', false, "Example: Nike")
        this.subscribed = new QueryEditorCheckField('Notifications', '')

        this.actions = document.createElement('div')
        this.actions.setAttribute('class', 'query-editor-actions')

        const cancel = document.createElement('button')
        cancel.setAttribute('class', 'query-editor-actions-cancel')
        cancel.textContent = 'Cancel'
        cancel.addEventListener('click', () => this.oncancel())
        this.actions.appendChild(cancel)

        const submit = document.createElement('button')
        submit.setAttribute('class', 'query-editor-actions-submit')
        submit.textContent = 'Save'
        submit.addEventListener('click', () => {
            this.element.classList.add('disabled')
            try {
                this.attemptToSave()
            } finally {
                this.element.classList.remove('disabled')
            }
        })
        this.actions.appendChild(submit)

        if (this.adQueryId) {
            this.fetchInfo()
        } else {
            this.presentFields()
        }
    }

    private async fetchInfo() {
        this.element.replaceChildren(this.loader.element)
        let result
        try {
            result = await getAdQuery(this.session.sessionId, this.adQueryId)
        } catch (e) {
            this.showError(e.toString())
            return
        }
        this.showInfo(result)
    }

    private showError(e: string) {
        const errorMsg = document.createElement('div')
        errorMsg.setAttribute('class', 'query-editor-error-message')
        errorMsg.textContent = e
        this.element.replaceChildren(errorMsg)
        return
    }

    private showInfo(info: AdQueryResult) {
        this.nickname.setValue(info.nickname)
        this.query.setValue(info.query)
        this.matchTerms.setValue((info.filters.matchTerms || []).join(','))
        this.accountFilter.setValue(info.filters.accountFilter || '')
        this.subscribed.input.checked = info.subscribed
        this.presentFields();
    }

    private presentFields() {
        this.element.replaceChildren(
            this.nickname.element,
            this.query.element,
            this.matchTerms.element,
            this.accountFilter.element,
            this.subscribed.element,
            this.actions,
        )
    }

    private async attemptToSave() {
        let hasEmpty = false;
        [this.nickname, this.query].forEach((field) => {
            if (!field.input.value) {
                hasEmpty = true
                field.invalidWithReason('This field must not be empty')
            }
        })
        if (hasEmpty) {
            return
        }
        const filters: AdQueryFilters = {
            matchTerms: (
                this.matchTerms.input.value ?
                    this.matchTerms.input.value.split(',') :
                    null
            ),
            accountFilter: this.accountFilter.input.value || null,
        }
        try {
            if (this.adQueryId) {
                await updateAdQuery(this.session.sessionId, {
                    nickname: this.nickname.input.value,
                    query: this.query.input.value,
                    filters: filters,
                    adQueryId: this.adQueryId,
                    subscribed: this.subscribed.input.checked,
                })
            } else {
                await insertAdQuery(this.session.sessionId, {
                    nickname: this.nickname.input.value,
                    query: this.query.input.value,
                    filters: filters,
                }, this.subscribed.input.checked)
            }
        } catch (e) {
            // TODO: more granular error handling here
            this.nickname.invalidWithReason(e.toString())
            return
        }
        this.oncomplete()
    }
}

class QueryEditorField {
    public element: HTMLElement
    public input: HTMLInputElement
    private validatorField: HTMLElement

    constructor(private name: string, private value: string, required: boolean, hint: string) {
        this.element = document.createElement('div')
        this.element.setAttribute('class', 'query-editor-field')

        this.input = document.createElement('input')
        this.input.id = `query-editor-input-${name.replace(' ', '-').toLowerCase()}`
        this.input.setAttribute('placeholder', hint)
        this.input.setAttribute('class', 'query-editor-field-input')
        const label = document.createElement('label')
        label.setAttribute('for', this.input.id)
        label.setAttribute('class', 'query-editor-field-label')
        label.textContent = required ? `* ${name}` : name

        this.validatorField = document.createElement('div')
        this.validatorField.setAttribute('class', 'query-editor-field-validator')

        this.element.appendChild(label)
        this.element.appendChild(this.input)
        this.element.appendChild(this.validatorField)

        this.input.addEventListener('input', () => this.setValid(true))
    }

    public setValue(value: string) {
        this.input.value = value
        this.setValid(true)
    }

    public invalidWithReason(reason: string) {
        this.validatorField.textContent = reason
        this.setValid(false)
    }

    private setValid(valid: boolean) {
        if (valid) {
            this.element.classList.remove('query-editor-field-invalid')
        } else {
            this.element.classList.add('query-editor-field-invalid')
        }
    }
}

class QueryEditorCheckField extends QueryEditorField {
    constructor(name: string, value: string) {
        super(name, value, false, null)
        this.input.setAttribute('type', 'checkbox')
        this.element.classList.add('query-editor-field-checkbox')
    }
}