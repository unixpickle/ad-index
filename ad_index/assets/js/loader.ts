class Loader {
    public element: HTMLElement

    constructor() {
        this.element = document.createElement('div');
        this.element.setAttribute('class', 'loader');
    }
}
