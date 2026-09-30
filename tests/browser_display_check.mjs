// Reproduce the saved workflow's output display without queueing or saving it.
import { readFile, writeFile } from "node:fs/promises";
const version = await (await fetch("http://127.0.0.1:9227/json/version")).json();
const socket = new WebSocket(version.webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener("open", resolve, { once: true }));
let sequence = 0, session, context;
const pending = new Map();
socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (!message.id) return;
    const { resolve, reject, timer } = pending.get(message.id);
    clearTimeout(timer); pending.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
});
function cdp(method, params = {}, sessionId = session) {
    return new Promise((resolve, reject) => {
        const id = ++sequence;
        const timer = setTimeout(() => reject(new Error(`CDP timeout: ${method}`)), 20000);
        pending.set(id, { resolve, reject, timer });
        socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
}
async function evaluate(expression) {
    const result = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
}
async function until(expression) {
    for (let i = 0; i < 100; i++) {
        if (await evaluate(expression)) return;
        await new Promise(resolve => setTimeout(resolve, 400));
    }
    throw new Error(`Timed out: ${expression}`);
}
try {
    context = (await cdp("Target.createBrowserContext")).browserContextId;
    const target = await cdp("Target.createTarget", { url: "about:blank", browserContextId: context });
    session = (await cdp("Target.attachToTarget", { targetId: target.targetId, flatten: true })).sessionId;
    await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
    await cdp("Page.navigate", { url: "http://127.0.0.1:8188" });
    await cdp("Page.bringToFront");
    await until("Boolean(window.comfyAPI?.app?.app?.graph && window.LiteGraph?.registered_node_types?.RM_LLM)");
    await new Promise(resolve => setTimeout(resolve, 2000));
    const workflow = JSON.parse(await readFile(new URL('../../../user/default/workflows/RM-LLM.json', import.meta.url), 'utf8'));
    await evaluate(`(async()=>{
        window.rmApp=window.comfyAPI.app.app;
        await rmApp.loadGraphData(${JSON.stringify(workflow)});
        window.rmNode=rmApp.graph.getNodeById(1);
        rmApp.canvas.ds.scale=.8;rmApp.canvas.ds.offset=[6990,-6420];rmApp.graph.setDirtyCanvas(true,true);
    })()`);
    await until("rmNode.widgets.some(w=>w.name==='rm_row_temperature')");
    console.log('Saved workflow output display:', await evaluate(`(async()=>{
        const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const target=rmApp.graph.getNodeById(4),api=window.comfyAPI.api.api;
        const before=await rmApp.graphToPrompt();
        if(before.output['1'].inputs.system_prompt[0]!=='2'||before.output['1'].inputs.user_prompt[0]!=='3'||before.output['4'].inputs.anything[0]!=='1')throw Error('Saved wiring changed');
        for(const text of ['First generated response', 'Second generated response after rerunning']) {
            api.dispatchEvent(new CustomEvent('executed',{detail:{node:'4',display_node:'4',output:{text:[text]}}}));
            await new Promise(r=>setTimeout(r,300));await frame();
            const field=target.widgets.find(w=>w.name==='text'),rect=field.element.getBoundingClientRect();
            if(field.value!==text)throw Error('Output text missing');
            if(rect.width<300||rect.height<200||rect.x<0||rect.x>1440||rect.y<0||rect.y>1100)throw Error('Output widget not laid out: '+JSON.stringify({rect:rect.toJSON(),height:field.computedHeight,y:field.y,source:target.getInputNode(0)?.type,connected:field.element.isConnected,display:getComputedStyle(field.element).display}));
        }
        const after=await rmApp.graphToPrompt();
        if(JSON.stringify(before.output['1'].inputs)!==JSON.stringify(after.output['1'].inputs)||JSON.stringify(before.output['4'].inputs.anything)!==JSON.stringify(after.output['4'].inputs.anything))throw Error('Display changed RM-LLM execution inputs or output wiring');
        return {savedWorkflowWiring:true,firstResultVisible:true,repeatedResultVisible:true,executionInputsUnchanged:true};
    })()`));
    const screenshot = await cdp("Page.captureScreenshot", { format: "png" });
    await writeFile(new URL('./rm-llm-display-fixed.png', import.meta.url), Buffer.from(screenshot.data, 'base64'));
} finally {
    if (context) await cdp("Target.disposeBrowserContext", { browserContextId: context }, null);
    socket.close();
}
