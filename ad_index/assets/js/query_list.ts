class QueryList {
    session: SessionInfo
    queries: Array<AdQueryResult>
    element: HTMLDivElement
    loader: Loader

    constructor(session: SessionInfo) {
        this.session = session;
        this.queries = null;
        this.element = document.createElement('div');
        this.element.setAttribute('class', 'query-list');

        this.loader = new Loader();
        this.element.appendChild(this.loader.element);

        this._reload();
    }

    async _reload() {
        let results;
        try {
            results = await getAdQueries(this.session.sessionId);
        } catch (e) {
            this._showError(e.toString());
            return;
        }
        this._renderResults(results);
    }

    _showError(e: string) {
        const errorMsg = document.createElement('div');
        errorMsg.setAttribute('class', 'query-list-error-message');
        errorMsg.textContent = e;
        this.element.replaceChildren(errorMsg);
        return;
    }

    _renderResults(results: Array<AdQueryResult>) {
        if (results.length === 0) {
            const empty = document.createElement('div');
            empty.setAttribute('class', 'query-list-empty-message');
            empty.textContent = 'No queries have been added yet.';
            this.element.replaceChildren(empty);
            return;
        }
        const elements = results.map((info) => {
            const elem = document.createElement('div');
            elem.setAttribute('class', 'query-list-item');

            const nickname = document.createElement('label');
            nickname.setAttribute('class', 'query-list-item-nickname');
            nickname.textContent = info.nickname;
            elem.appendChild(nickname);

            const query = document.createElement('label');
            query.setAttribute('class', 'query-list-item-query');
            query.textContent = info.query;
            elem.appendChild(query);

            const subRow = document.createElement('div');
            subRow.setAttribute('class', 'query-list-item-subscription')
            const subCheckbox = document.createElement('input');
            subCheckbox.setAttribute('type', 'checkbox');
            subCheckbox.setAttribute('class', 'query-list-item-subscription-input');
            subCheckbox.id = `${Math.random()}${Math.random()}`;
            subCheckbox.checked = info.subscribed;
            subRow.appendChild(subCheckbox);
            const subCheckboxLabel = document.createElement('label');
            subCheckboxLabel.setAttribute('class', 'query-list-item-subscription-label');
            subCheckboxLabel.setAttribute('for', subCheckbox.id);
            subCheckboxLabel.textContent = 'Notify me';
            subRow.appendChild(subCheckboxLabel);
            elem.appendChild(subRow);

            subCheckbox.addEventListener('input', () => {
                const checked = subCheckbox.checked;
                subRow.classList.add('disabled');
                toggleAdQuerySubscription(
                    this.session.sessionId,
                    info.adQueryId,
                    checked,
                ).catch((_) => {
                    subCheckbox.checked = info.subscribed;
                }).finally(() => {
                    subRow.classList.remove('disabled');
                });
            });

            return elem;
        });
        this.element.replaceChildren(...elements);
    }
}