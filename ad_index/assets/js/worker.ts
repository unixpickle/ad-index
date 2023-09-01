/// <reference lib="webworker" />

const ctx: ServiceWorkerGlobalScope = (self as any)

interface NotificationPayload {
    adQueryId: string
    nickname: string
    ad: {
        id: string
        accountName: string
        accountUrl: string
        text: string
    }
}

function receivePushNotification(event: PushEvent) {
    const payload: NotificationPayload = event.data.json()
    const title = `New Ad: ${payload.nickname}`
    const options = {
        data: `${location.origin}/#view/${payload.adQueryId}`,
        body: `Ad detected with content: ${payload.ad.text}`,
        vibrate: [200, 100, 200],
    }
    event.waitUntil(ctx.registration.showNotification(title, options))
}

function notificationClicked(event: NotificationEvent) {
    event.preventDefault();
    const url = event.notification.data;

    // https://stackoverflow.com/questions/39418545/chrome-push-notification-how-to-open-url-adress-after-click
    event.notification.close()
    event.waitUntil(ctx.clients.openWindow(url))
}

ctx.addEventListener('push', receivePushNotification)
ctx.addEventListener('notificationclick', notificationClicked)