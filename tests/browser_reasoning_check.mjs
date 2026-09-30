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
    context=(await cdp('Target.createBrowserContext')).browserContextId;
    const target=await cdp('Target.createTarget',{url:'about:blank',browserContextId:context});
    session=(await cdp('Target.attachToTarget',{targetId:target.targetId,flatten:true})).sessionId;
    await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1400,deviceScaleFactor:1,mobile:false});
    await cdp('Page.navigate',{url:'http://127.0.0.1:8188'});await cdp('Page.bringToFront');
    await until('Boolean(window.comfyAPI?.app?.app?.graph && window.LiteGraph?.registered_node_types?.RM_LLM_V2)');
    await new Promise(resolve=>setTimeout(resolve,2000));
    await evaluate(`(async()=>{
        window.rmApp=window.comfyAPI.app.app;
        await rmApp.loadGraphData({last_node_id:0,last_link_id:0,nodes:[],links:[],groups:[],config:{},extra:{},version:.4});
        window.rmNode=LiteGraph.createNode('RM_LLM_V2');rmApp.graph.add(rmNode);
        rmNode.widgets.find(w=>w.name==='model_name').value='moonshotai/kimi-k3';
        rmNode.onConfigure(rmNode.serialize());
        rmNode.pos=[80,150];rmApp.canvas.ds.scale=1;rmApp.canvas.ds.offset=[0,0];
    })()`);
    await until("rmNode.widgets.some(w=>w.name==='rm_row_reasoning.enabled')");
    console.log('Live Kimi K3 controls:',await evaluate(`(async()=>{
        const assert=(v,m)=>{if(!v)throw Error(m)},row=n=>rmNode.widgets.find(w=>w.name==='rm_row_'+n);
        const params=()=>JSON.parse(rmNode.widgets.find(w=>w.name==='parameters_json').value);
        const toggle=()=>row('reasoning.enabled').element.querySelector('input');
        assert(toggle().checked,'Kimi advertised On default');
        assert(Object.keys(params()).length===0,'Default is omitted');
        assert(row('reasoning.enabled').element.querySelector('label').textContent==='Thinking/Reasoning','Unified label');
        row('heading_standard').element.querySelector('button').click();
        const simple=rmNode.widgets.filter(w=>w.element?.dataset.section==='standard');
        assert(simple.at(-1).name==='rm_row_reasoning.enabled','Toggle bottom of Simple');
        assert(!row('reasoning.enabled').hidden,'Toggle visible in Simple');
        const effort=row('reasoning_effort').element.querySelector('select');
        assert(JSON.stringify([...effort.options].map(o=>o.value))===JSON.stringify(['','max','high','low']),'Model-specific efforts');
        const raw=row('reasoning').element.querySelector('textarea');
        raw.value=JSON.stringify({effort:'high',exclude:true});raw.dispatchEvent(new Event('change'));
        let input=toggle();input.checked=false;input.dispatchEvent(new Event('input'));
        assert(JSON.stringify(params().reasoning)===JSON.stringify({exclude:true,enabled:false}),'Off preserves exclude and removes effort');
        input=toggle();input.checked=true;input.dispatchEvent(new Event('input'));
        assert(params().reasoning.enabled===true && params().reasoning.exclude===true,'On preserves unrelated values');
        input=toggle();input.checked=false;input.dispatchEvent(new Event('input'));
        const select=row('reasoning_effort').element.querySelector('select');select.value='low';select.dispatchEvent(new Event('change'));
        assert(params().reasoning.enabled===true && params().reasoning_effort==='low' && toggle().checked,'Effort updates toggle');
        const source=LiteGraph.createNode('PrimitiveBoolean');rmApp.graph.add(source);
        source.connect(0,rmNode,rmNode.inputs.findIndex(i=>i.name==='reasoning.enabled'));
        assert(toggle().disabled,'Connected toggle disabled');
        const prompt=await rmApp.graphToPrompt();
        assert(Array.isArray(prompt.output[rmNode.id].inputs['reasoning.enabled']),'Boolean input serialized');
        rmNode.disconnectInput(rmNode.inputs.findIndex(i=>i.name==='reasoning.enabled'));rmApp.graph.remove(source);
        window.rmCaps=await (await fetch('/rm_llm/capabilities',{method:'POST',headers:{'Content-Type':'application/json','X-RM-LLM':'1'},body:JSON.stringify({provider:'OpenRouter',model:'moonshotai/kimi-k3'})})).json();
        rmCaps.reasoning_options.mandatory=true;
        const api=window.comfyAPI.api.api,original=api.fetchApi;
        api.fetchApi=async function(url,options){if(url==='/rm_llm/capabilities')return new Response(JSON.stringify(rmCaps),{status:200});return original.call(this,url,options);};
        rmNode.widgets.find(w=>w.name==='parameters_json').value='{}';rmNode.onConfigure(rmNode.serialize());
        return {liveDefaults:true,unifiedToggle:true,bottomOfSimple:true,effortChoices:true,onOffPayload:true,connectedBoolean:true};
    })()`));
    await until("rmNode.widgets.find(w=>w.name==='rm_row_reasoning.enabled')?.element.querySelector('input')?.disabled");
    console.log('Mandatory reasoning:',await evaluate(`(()=>{
        const row=rmNode.widgets.find(w=>w.name==='rm_row_reasoning.enabled'),input=row.element.querySelector('input');
        if(!input.checked||!input.disabled)throw Error('Mandatory reasoning must remain on');
        if(rmNode.widgets.find(w=>w.name==='parameters_json').value!=='{}')throw Error('Mandatory default should remain omitted');
        return {lockedOn:true,defaultOmitted:true};
    })()`));
} finally {
    if(context)await cdp('Target.disposeBrowserContext',{browserContextId:context},null);
    socket.close();
}
