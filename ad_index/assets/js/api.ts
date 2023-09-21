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

interface AdQueryFilters {
    matchTerms: string[]
    rejectTerms: string[]
    accountFilter: string
}

interface AdQueryBase {
    nickname: string
    query: string
    filters: AdQueryFilters
}

interface AdQuery extends AdQueryBase {
    adQueryId: string
}

interface AdQueryResult extends AdQuery {
    subscribed: boolean
}

interface AdQueryStatus extends AdQueryResult {
    nextPull: number

    // These may be null
    lastPull: number
    lastError: number
    lastNotify: number
}

interface AdContent {
    adQueryId: number
    id: string
    accountName: string
    accountUrl: string
    startDate: number
    lastSeen: number
    text: string
}

async function createSession(): Promise<SessionInfo> {
    return extractSuccess(await (await fetch('/api/create_session')).json())
}

async function sessionExists(sessionId: string): Promise<boolean> {
    const uri = `/api/session_exists?session_id=${encodeURIComponent(sessionId)}`
    return extractSuccess(await (await fetch(uri)).json())
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

async function getAdQueries(sessionId: string): Promise<AdQueryResult[]> {
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

async function getAdQueryStatus(sessionId: string, adQueryId: string): Promise<AdQueryStatus> {
    const uri = (
        `/api/get_ad_query_status?session_id=${encodeURIComponent(sessionId)}` +
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

async function clearAdQuery(adQueryId: string) {
    const uri = `api/clear_ad_query?ad_query_id=${encodeURIComponent(adQueryId)}`
    return extractSuccess(await (await fetch(uri)).json())
}

async function deleteAdQuery(adQueryId: string) {
    const uri = `/api/delete_ad_query?ad_query_id=${encodeURIComponent(adQueryId)}`
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

async function listAdContent(adQueryId: string): Promise<AdContent[]> {
    const uri = `/api/list_ad_content?ad_query_id=${encodeURIComponent(adQueryId)}`
    return extractSuccess(await (await fetch(uri)).json())
}

function extractSuccess<T>(obj: any): T {
    const resp = obj as APIResponse<T>
    if (resp.error) {
        throw new ServerError(resp.error)
    } else {
        return resp.data
    }
}