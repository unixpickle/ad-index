/// <reference lib="webworker" />

const ctx: ServiceWorkerGlobalScope = (self as any)

function receivePushNotification(event: PushEvent) {
    const title = "Hello world!"
    const options = {
        data: "hello",
        body: event.data.json(),
        vibrate: [200, 100, 200],
    }
    event.waitUntil(ctx.registration.showNotification(title, options))
}

ctx.addEventListener('push', receivePushNotification)