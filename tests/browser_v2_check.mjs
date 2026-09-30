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
    await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1400, deviceScaleFactor: 1, mobile: false });
    await cdp("Page.navigate", { url: "http://127.0.0.1:8188" });
    await cdp("Page.bringToFront");
    await until("Boolean(window.comfyAPI?.app?.app?.graph && window.LiteGraph?.registered_node_types?.RM_LLM_V2)");
    await new Promise(resolve => setTimeout(resolve, 2000));
    await evaluate(`(async()=>{
        window.rmApp = window.comfyAPI.app.app;
        const api = window.comfyAPI.api.api, original = api.fetchApi;
        window.rmRefreshCalls=[];window.rmRefreshFail=false;
        api.fetchApi = async function(url, options) {
            if(url==='/rm_llm/refresh'||url==='/rm_llm/models'){
                rmRefreshCalls.push(url);await new Promise(r=>setTimeout(r,20));
                return new Response(JSON.stringify(rmRefreshFail?{error:'Synthetic refresh failed'}:url.endsWith('/models')?{models:[{id:'synthetic/test'}]}:{}),{status:rmRefreshFail?400:200});
            }
            if(url === '/rm_llm/capabilities') return new Response(JSON.stringify({
                provider:'Featherless', source:'Synthetic browser test', record_updated:'test', input_modalities:['text','image','video'],
                parameters:{temperature:{type:'number'},top_p:{type:'number'},chat_template_kwargs:{type:'object'}},
                template_parameters:{enable_thinking:{type:'boolean',default:false}},
                endpoints:[{id:'Auto',parameters:['temperature','top_p','chat_template_kwargs']}] }),{status:200,headers:{'Content-Type':'application/json'}});
            return original.call(this,url,options);
        };
        await rmApp.loadGraphData({last_node_id:0,last_link_id:0,nodes:[],links:[],groups:[],config:{},extra:{},version:.4});
        window.rmNode = LiteGraph.createNode('RM_LLM_V2'); rmApp.graph.add(rmNode);
        rmNode.widgets.find(w=>w.name==='model_name').value='synthetic/test';
        rmNode.onConfigure(rmNode.serialize());
        rmNode.pos=[80,150]; rmApp.canvas.ds.scale=1;rmApp.canvas.ds.offset=[0,0];
    })()`);
    await until("rmNode.widgets.some(w=>w.name==='rm_row_top_p')");
    console.log(await evaluate(`(async()=>{
        const assert=(v,msg)=>{if(!v)throw Error(msg)};
        const row=name=>rmNode.widgets.find(w=>w.name==='rm_row_'+name);
        const field=name=>row(name).element.querySelector('input');
        const params=()=>JSON.parse(rmNode.widgets.find(w=>w.name==='parameters_json').value);
        const change=(name,v)=>{const f=field(name);f.value=v;f.dispatchEvent(new Event('input',{bubbles:true}));};
        assert(['model','standard','advanced'].every(name=>rmNode.properties.rm_llm_sections[name]===false),'All sections initially collapsed');
        assert(row('provider').hidden && row('user_prompt').hidden && row('temperature').hidden,'Initial contents hidden');
        row('heading_model').element.querySelector('button').click();
        row('heading_standard').element.querySelector('button').click();
        const rows=rmNode.widgets.filter(w=>w.name.startsWith('rm_row_')).map(w=>w.name.replace('rm_row_',''));
        assert(JSON.stringify(rows.slice(0,7))===JSON.stringify(['model_heading','section_3','heading_model','provider','model_name','credential_source','api_key_env']),'Model row order: '+rows);
        assert(JSON.stringify(rows.slice(rows.indexOf('heading_standard'),rows.indexOf('heading_advanced')))===JSON.stringify(['heading_standard','image','video','system_prompt','user_prompt','creativity','chat_template_kwargs.enable_thinking']),'Simple row order');
        assert(row('credential_source').element.textContent.includes('API Key System'),'API Key System label');
        assert(row('api_key_env').hidden && !rmNode.inputs.some(i=>i.name==='api_key_env'),'Environment name removed from panel and sockets');
        assert(row('section_3').element.textContent.includes('  |  Output limit:') && row('section_3').element.textContent.startsWith('Context:'),'Only context and output limit');
        assert(row('section_4').hidden && row('section_1').hidden,'No idle status gaps');
        const refresh=row('section_2').element.querySelector('input');
        assert(refresh.getAttribute('role')==='switch','Refresh is toggle');
        refresh.click();assert(refresh.checked&&refresh.disabled,'Refresh on while busy');
        for(let i=0;i<30&&refresh.disabled;i++)await new Promise(r=>setTimeout(r,20));
        assert(!refresh.checked&&!refresh.disabled,'Refresh returns off');
        assert(rmRefreshCalls.join(',')==='/rm_llm/refresh,/rm_llm/models','Refresh actions unchanged');
        const timestamp=row('section_2').element.textContent;
        assert(timestamp.includes('Last refreshed:')&&!timestamp.includes('Not yet'),'Refresh date/time shown beside toggle');
        rmRefreshFail=true;refresh.click();
        for(let i=0;i<30&&refresh.disabled;i++)await new Promise(r=>setTimeout(r,20));
        assert(!refresh.checked&&!row('section_4').hidden,'Failed refresh resets toggle and shows error');
        assert(row('section_2').element.textContent===timestamp,'Failed refresh preserves last successful time');
        rmRefreshFail=false;refresh.click();
        for(let i=0;i<30&&refresh.disabled;i++)await new Promise(r=>setTimeout(r,20));
        const apiMode=row('credential_source').element.querySelector('select');
        apiMode.value='Masked session key';apiMode.dispatchEvent(new Event('change'));
        assert(!row('section_0').hidden && row('section_0').element.dataset.section==='model','Masked key entry in Model');
        row('heading_model').element.querySelector('button').click();
        for(const name of ['provider','model_name','credential_source','api_key_env','section_0','section_1','timeout_seconds','section_2','section_4'])assert(row(name).hidden,'Model collapses '+name);
        assert(!row('user_prompt').hidden,'Simple independent of Model');
        assert(!row('section_3').hidden,'Limits stay visible with Model collapsed');
        assert(getComputedStyle(row('section_3').element.querySelector('.rm-note')).fontSize==='12px','Limits fixed font size');
        const folded=rmNode.serialize();rmNode.configure(folded);await new Promise(r=>setTimeout(r,100));
        assert(row('provider').hidden && row('user_prompt').hidden,'Load collapses Model and Simple');
        row('heading_standard').element.querySelector('button').click();
        row('heading_model').element.querySelector('button').click();
        assert(!row('section_0').hidden,'Masked key restored on expand');
        apiMode.value='Environment variable';apiMode.dispatchEvent(new Event('change'));
        assert(row('section_0').hidden,'Masked key hidden for environment mode');
        assert(row('heading_standard').element.textContent.includes('Simple'),'Simple title');
        assert(row('temperature').hidden && row('top_p').hidden,'Advanced sampling folded');
        assert(row('console_output').hidden,'Console inside collapsed Advanced');
        assert(rows[rows.indexOf('heading_advanced')+1]==='temperature','Temperature first in Advanced');
        assert(Object.keys(params()).length===0,'Invented defaults');
        assert(!row('chat_template_kwargs.enable_thinking').element.textContent.includes('(default)'),'Default suffix');
        change('creativity',50);
        assert(params().temperature===.49,'Temperature curve');
        assert(params().top_p===.97,'top_p curve');
        assert(Math.abs(Number(field('temperature').value)-params().temperature)<1e-10,'Advanced sync');
        const oldP=params().top_p;change('temperature',1.2);
        assert(params().top_p===oldP && Math.abs(Number(field('creativity').value)-100)<.01,'Independent temp inverse');
        assert(field('creativity').getAttribute('aria-valuetext').includes('Custom'),'Accessible custom pair status');
        change('top_p',.9);
        assert(params().temperature===1.2 && Number(field('creativity').value)===0,'Independent top_p inverse');
        const saved=rmNode.serialize();rmNode.configure(saved);
        await new Promise(r=>setTimeout(r,100));
        assert(params().temperature===1.2 && params().top_p===.9 && Number(field('creativity').value)===0,'Roundtrip custom values');
        assert(['model','standard','advanced'].every(name=>rmNode.properties.rm_llm_sections[name]===false),'Expanded saved sections load collapsed');
        row('heading_model').element.querySelector('button').click();
        row('heading_standard').element.querySelector('button').click();
        change('creativity',100);
        assert(Math.abs(params().temperature-1.2)<1e-10 && params().top_p===.99,'Slider re-link');
        assert(!row('creativity').element.querySelector('button'),'No Default button');
        assert([...row('creativity').element.querySelectorAll('span')].map(s=>s.textContent).join(',')==='Min,Max','Only Min and Max labels');
        change('temperature','');change('top_p','');assert(Object.keys(params()).length===0,'Default omission');
        const source=LiteGraph.createNode('PrimitiveFloat');rmApp.graph.add(source);
        source.connect(0,rmNode,rmNode.inputs.findIndex(i=>i.name==='creativity'));
        assert(field('creativity').disabled && field('temperature').disabled && field('top_p').disabled,'Connected creativity');
        let prompt=await rmApp.graphToPrompt();
        assert(Array.isArray(prompt.output[rmNode.id].inputs.creativity),'Creativity API link');
        rmNode.disconnectInput(rmNode.inputs.findIndex(i=>i.name==='creativity'));
        assert(!field('creativity').disabled && !field('temperature').disabled,'Disconnected creativity');
        row('heading_standard').element.querySelector('button').click();
        assert(!row('provider').hidden && !row('model_name').hidden && row('creativity').hidden,'Fixed provider/model');
        row('heading_standard').element.querySelector('button').click();
        row('heading_advanced').element.querySelector('button').click();
        assert(!row('temperature').hidden && !row('top_p').hidden && !row('console_output').hidden,'Advanced expand');
        source.connect(0,rmNode,rmNode.inputs.findIndex(i=>i.name==='temperature'));
        change('creativity',50); prompt=await rmApp.graphToPrompt();
        assert(Array.isArray(prompt.output[rmNode.id].inputs.temperature),'Independent temperature API link');
        assert(!Object.hasOwn(prompt.output[rmNode.id].inputs,'creativity'),'Slider is serialized as sampling values');
        rmNode.disconnectInput(rmNode.inputs.findIndex(i=>i.name==='temperature'));
        rmApp.graph.remove(source);
        const old=LiteGraph.createNode('RM_LLM');rmApp.graph.add(old);
        assert(old.widgets.find(w=>w.name==='rm_row_heading_standard').element.textContent.includes('Standard'),'Original node title');
        assert(!old.widgets.some(w=>w.name==='rm_row_creativity'),'Original node changed');rmApp.graph.remove(old);
        row('heading_advanced').element.querySelector('button').click();
        row('heading_model').element.querySelector('button').click();
        rmNode.setSize([620,rmNode.computeSize()[1]]);rmApp.graph.setDirtyCanvas(true,true);
        await new Promise(r=>setTimeout(r,300));
        const inputIndex=rmNode.inputs.findIndex(i=>i.name==='creativity');
        const pos=rmNode.getInputPos(inputIndex), labelRect=row('creativity').element.querySelector('label').getBoundingClientRect();
        const canvasRect=rmApp.canvas.canvas.getBoundingClientRect();
        const socketY=canvasRect.y+(pos[1]+rmApp.canvas.ds.offset[1])*rmApp.canvas.ds.scale;
        assert(Math.abs(socketY-labelRect.y-labelRect.height/2)<1,'Creativity socket alignment');
        assert(rmApp.canvas.graph.getNodeById(rmNode.id)===rmNode,'Visible canvas uses tested graph');
        const rect=field('creativity').getBoundingClientRect();
        assert(rect.width>100 && rect.height>10 && rect.y>0 && rect.y<1400,'Slider visible on canvas: '+JSON.stringify(rect.toJSON()));
        const sliderStyle=getComputedStyle(field('creativity')), toggleStyle=getComputedStyle(field('chat_template_kwargs.enable_thinking'));
        assert(sliderStyle.height===toggleStyle.height && sliderStyle.height==='24px','Slider matches toggle height');
        assert(sliderStyle.borderRadius===toggleStyle.borderRadius,'Slider matches toggle pill');
        assert(rect.height===field('chat_template_kwargs.enable_thinking').getBoundingClientRect().height,'Actual outer heights match');
        assert(sliderStyle.backgroundImage.includes('35, 122, 175'),'Blue slider fill');
        assert(Number(field('creativity').value)===50,'Rounded values preserve slider position');
        const modelWidget=rmNode.widgets.find(w=>w.name==='model_name');
        const originalModel=modelWidget.value;
        const heading=row('model_heading').element;
        for(const width of [350,500,800]) {
            rmNode.setSize([width,rmNode.size[1]]);
            await new Promise(r=>setTimeout(r,100));
            const text=heading.querySelector('.rm-model-name');
            assert(text.textContent===originalModel,'Model heading available without canvas drawing');
            assert(text.scrollHeight<=56 && text.scrollWidth<=text.clientWidth,'Model preview fits');
            assert(getComputedStyle(heading).backgroundColor==='rgba(0, 0, 0, 0)','No heading box');
        }
        modelWidget.value=originalModel;
        row('heading_standard').element.querySelector('button').click();
        row('heading_model').element.querySelector('button').click();
        rmNode.setSize([620,rmNode.computeSize()[1]]);rmApp.graph.setDirtyCanvas(true,true);
        await new Promise(r=>setTimeout(r,300));
        return {layout:true,curve:true,independentInverse:true,roundtrip:true,providerDefaults:true,connectedInputs:true,originalPreserved:true,collapsedOnLoad:true,modelPreviewFits:true};
    })()`));
    const screenshot=await cdp('Page.captureScreenshot',{format:'png'});
    await writeFile(new URL('./rm-llm-v2.png',import.meta.url),Buffer.from(screenshot.data,'base64'));
} finally {
    if(context) await cdp('Target.disposeBrowserContext',{browserContextId:context},null);
    socket.close();
}
