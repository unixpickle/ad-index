class ServerError extends Error {
}

interface APIResponse<T> {
    data: T
    error: string
}

interface SessionInfo {
    sessionId: string
    vapidPub: string
}

interface AdQueryBase {
    nickname: string
    query: string
    filters: Array<String>
}

interface AdQuery extends AdQueryBase {
    adQueryId: string
}

interface AdQueryResult extends AdQuery {
    subscribed: boolean
}

async function createSession(): Promise<SessionInfo> {
    return extractSuccess(await (await fetch('/api/create_session')).json())
}

async function updatePushSub(sessionId: string, pushSub: string) {
    if (!pushSub) {
        pushSub = null
    }
    const uri = (
        `/api/update_push_sub?session_id=${encodeURIComponent(sessionId)}`
        + `&push_sub=${encodeURIComponent(pushSub)}`
    )
    return extractSuccess(await (await fetch(uri)).json())
}

async function getAdQueries(sessionId: string): Promise<Array<AdQueryResult>> {
    const uri = `/api/get_ad_queries?session_id=${encodeURIComponent(sessionId)}`
    return extractSuccess(await (await fetch(uri)).json())
}

async function getAdQuery(sessionId: string, adQueryId: string): Promise<AdQueryResult> {
    const uri = (
        `/api/get_ad_query?session_id=${encodeURIComponent(sessionId)}` +
        `&ad_query_id=${encodeURIComponent(adQueryId)}`
    )
    return extractSuccess(await (await fetch(uri)).json())
}

async function insertAdQuery(sessionId: string, info: AdQueryBase, subscribed: boolean) {
    const uri = (
        `/api/insert_ad_query?session_id=${encodeURIComponent(sessionId)}`
        + `&nickname=${encodeURIComponent(info.nickname)}`
        + `&query=${encodeURIComponent(info.query)}`
        + `&filters=${encodeURIComponent(JSON.stringify(info.filters))}`
        + `&subscribed=${encodeURIComponent(JSON.stringify(subscribed))}`
    )
    return extractSuccess(await (await fetch(uri)).json())
}

async function updateAdQuery(sessionId: string, info: AdQueryResult) {
    const uri = (
        `/api/update_ad_query?session_id=${encodeURIComponent(sessionId)}`
        + `&ad_query_id=${encodeURIComponent(info.adQueryId)}`
        + `&nickname=${encodeURIComponent(info.nickname)}`
        + `&query=${encodeURIComponent(info.query)}`
        + `&filters=${encodeURIComponent(JSON.stringify(info.filters))}`
        + `&subscribed=${encodeURIComponent(JSON.stringify(info.subscribed))}`
    )
    return extractSuccess(await (await fetch(uri)).json())
}

async function toggleAdQuerySubscription(sessionId: string, adQueryId: string, subscribed: boolean) {
    const uri = (
        `/api/toggle_ad_query_subscription?session_id=${encodeURIComponent(sessionId)}`
        + `&ad_query_id=${encodeURIComponent(adQueryId)}`
        + `&subscribed=${encodeURIComponent(JSON.stringify(subscribed))}`
    )
    extractSuccess(await (await fetch(uri)).json())
}

function extractSuccess<T>(obj: any): T {
    const resp = obj as APIResponse<T>
    if (resp.error) {
        throw new ServerError(resp.error)
    } else {
        return resp.data
    }
}