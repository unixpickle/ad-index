const ctx: Worker = self as any;
ctx.onmessage = (e: MessageEvent) => {
    console.log('got a message from worker ' + e);
};
