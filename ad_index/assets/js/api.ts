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

async function createSession(): Promise<SessionInfo> {
    return extractSuccess(await (await fetch('/api/create_session')).json());
}

async function updatePushSub(sessionId: string, pushSub: string) {
    if (!pushSub) {
        pushSub = null;
    }
    const uri = (
        `/api/update_push_sub?session_id=${encodeURIComponent(sessionId)}`
        + `&push_sub=${encodeURIComponent(pushSub)}`
    );
    return extractSuccess(await fetch(uri));
}

function extractSuccess<T>(obj: any): T {
    const resp = obj as APIResponse<T>;
    if (resp.error) {
        throw new ServerError(resp.error);
    } else {
        return resp.data;
    }
}