// Uses local Edge's DevTools port. No packages or generation calls required.
import { writeFile } from "node:fs/promises";
const pages = await (await fetch("http://127.0.0.1:9227/json/list")).json();
const socket = new WebSocket(pages.find(p => p.type === "page").webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener("open", resolve, { once: true }));
let sequence = 0;
const pending = new Map();
const exceptions = [];
socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.id) {
        const pair = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) pair.reject(new Error(JSON.stringify(message.error)));
        else pair.resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown") {
        exceptions.push(message.params.exceptionDetails);
    }
});
function cdp(method, params = {}) {
    return new Promise((resolve, reject) => {
        const id = ++sequence;
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
    });
}
async function evaluate(expression) {
    const r = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
    return r.result?.value;
}
async function until(expression, timeout = 60000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
        if (await evaluate(expression)) return;
        await new Promise(resolve => setTimeout(resolve, 400));
    }
    throw new Error(`Timed out: ${expression}`);
}
try {
    await cdp("Runtime.enable");
    await cdp("Page.enable");
    await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1200, deviceScaleFactor: 1, mobile: false });
    await cdp("Page.navigate", { url: "about:blank" });
    await until("location.href === 'about:blank' && !window.comfyAPI");
    await cdp("Page.navigate", { url: "http://127.0.0.1:8188" });
    await until("Boolean(window.comfyAPI?.app?.app?.graph && window.LiteGraph?.registered_node_types?.RM_LLM)");
    await new Promise(r=>setTimeout(r,2000));
    await evaluate(`(() => {
        window.rmApp=window.comfyAPI.app.app;
        for(const n of [...rmApp.graph._nodes]) {if(n.type==="RM_LLM")rmApp.graph.remove(n);else n.pos=[-10000,-10000];}
        window.rmNode=LiteGraph.createNode('RM_LLM');rmApp.graph.add(rmNode);
        rmNode.pos=[350,200];rmApp.canvas.ds.scale=0.8;rmApp.canvas.ds.offset=[0,0];
        window.row=(name)=>rmNode.widgets.find(w=>w.name==='rm_row_'+name)?.element;
        window.control=(name)=>row(name)?.querySelector('input,select,textarea,button');
        rmNode.widgets.find(w=>w.name==='provider').value='Featherless';
        rmNode.widgets.find(w=>w.name==='model_name').value='AEON-7/DFlash-Qwen3.5-27B-Uncensored';
        rmNode.onConfigure({});
    })()`);
    await until("!!control('temperature')?.isConnected");
    console.log('Sections and switches:', await evaluate(`(async () => {
        const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const rows=()=>rmNode.widgets.filter(w=>w.name.startsWith('rm_row_')&&!w.hidden).map(w=>w.name.slice(7));
        const expected=['heading_standard','image','provider','model_name','system_prompt','user_prompt','chat_template_kwargs.enable_thinking','temperature','heading_advanced'];
        if(JSON.stringify(rows())!==JSON.stringify(expected))throw new Error('Wrong Standard order: '+JSON.stringify(rows()));
        if(row('heading_advanced').querySelector('button').getAttribute('aria-expanded')!=='false')throw new Error('Advanced should start folded');
        for(const name of ['heading_standard','heading_advanced'])if(getComputedStyle(row(name).querySelector('button')).fontSize!=='18px')throw new Error('Section heading font size not applied');
        if(rmNode.getInputPos(rmNode.inputs.findIndex(i=>i.name==='top_k')).every(Number.isFinite))throw new Error('Hidden input left a hit target');
        const before=rmNode.size[1],think=control('chat_template_kwargs.enable_thinking');
        if(think.type!=='checkbox'||think.getAttribute('role')!=='switch')throw new Error('Thinking is not a toggle');
        const read=()=>JSON.parse(rmNode.widgets.find(w=>w.name==='parameters_json').value);
        if(read().chat_template_kwargs?.enable_thinking!==undefined)throw new Error('Default became explicit');
        think.click();if(read().chat_template_kwargs?.enable_thinking!==think.checked)throw new Error('Toggle did not store boolean');
        think.click();if(read().chat_template_kwargs?.enable_thinking!==think.checked)throw new Error('Toggle did not reverse');
        row('chat_template_kwargs.enable_thinking').querySelector('button').click();
        if(read().chat_template_kwargs?.enable_thinking!==undefined)throw new Error('Reset did not omit value');
        row('heading_advanced').querySelector('button').click();await frame();
        if(rmNode.size[1]<=before)throw new Error('Expanded section did not grow');
        const booleans=[...document.querySelectorAll('.rm-widget-row input[role=switch]')];
        if(booleans.length<3)throw new Error('Missing boolean switches');
        return {standardOrder:true,defaultOmitted:true,toggleOnOff:true,reset:true,advancedExpands:true};
    })()`));
    await until("!!control('top_k')?.isConnected");
    console.log('Alignment and resizing:',await evaluate(`(async () => {
        const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        window.checkAlignment=()=> {
            const canvas=rmApp.canvas.canvas.getBoundingClientRect(),scale=rmApp.canvas.ds.scale,offset=rmApp.canvas.ds.offset;
            let checked=0;
            for(const [index,input] of rmNode.inputs.entries()) {
                const label=row(input.name)?.querySelector('label');if(!label || rmNode.widgets.find(w=>w.name==='rm_row_'+input.name)?.hidden)continue;
                const rect=label.getBoundingClientRect(),pos=rmNode.getInputPos(index);
                const x=canvas.x+(pos[0]+offset[0])*scale,y=canvas.y+(pos[1]+offset[1])*scale;
                if(Math.abs(y-(rect.y+rect.height/2))>1 || x>=rect.x)throw new Error('Misaligned socket: '+input.name);
                if(y>110 && y<1180 && document.elementFromPoint(x,y)!==rmApp.canvas.canvas)throw new Error('DOM covers socket: '+input.name+' '+document.elementFromPoint(x,y)?.outerHTML.slice(0,800));
                checked++;
            }
            return checked;
        };
        await frame();const initial=checkAlignment(),smallHeight=control('system_prompt').clientHeight;
        const originalHeight=rmNode.size[1];rmNode.setSize([720,originalHeight+400]);rmApp.graph.setDirtyCanvas(true,true);await frame();
        checkAlignment();if(control('system_prompt').clientHeight<=smallHeight)throw new Error('Prompt did not grow '+JSON.stringify({before:smallHeight,after:control('system_prompt').clientHeight,node:rmNode.size,widget:rmNode.widgets.find(w=>w.name==='rm_row_system_prompt').computedHeight}));
        rmNode.setSize([520,originalHeight]);rmApp.graph.setDirtyCanvas(true,true);await frame();checkAlignment();
        rmApp.canvas.ds.scale=.6;rmApp.canvas.ds.offset=[50,-250];rmApp.graph.setDirtyCanvas(true,true);await frame();checkAlignment();
        return {settingsAligned:initial,resizeAndZoom:true};
    })()`));
    const drag=await evaluate(`(async () => {
        window.mouseSource=LiteGraph.createNode('PrimitiveStringMultiline');rmApp.graph.add(mouseSource);
        mouseSource.pos=[-60,rmNode.pos[1]+rmNode.widgets.find(w=>w.name==='rm_row_system_prompt').y];
        mouseSource.widgets.find(w=>w.name==='value').value='Mouse-connected prompt';
        rmApp.graph.setDirtyCanvas(true,true);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const canvas=rmApp.canvas.canvas.getBoundingClientRect(),scale=rmApp.canvas.ds.scale,offset=rmApp.canvas.ds.offset;
        const screen=p=>({x:canvas.x+(p[0]+offset[0])*scale,y:canvas.y+(p[1]+offset[1])*scale});
        return {from:screen(mouseSource.getOutputPos(0)),to:screen(rmNode.getInputPos(rmNode.inputs.findIndex(i=>i.name==='system_prompt')))};
    })()`);
    await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',...drag.from});
    await cdp('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...drag.from});
    for(let i=1;i<=10;i++)await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',buttons:1,x:drag.from.x+(drag.to.x-drag.from.x)*i/10,y:drag.from.y+(drag.to.y-drag.from.y)*i/10});
    await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...drag.to});
    console.log('Mouse connection:',await evaluate(`(() => {
        const index=rmNode.inputs.findIndex(i=>i.name==='system_prompt');
        if(rmNode.inputs[index].link==null)throw new Error('Mouse could not connect aligned socket');
        rmNode.disconnectInput(index);rmApp.graph.remove(mouseSource);return {dragToSettingSocket:true};
    })()`));
    console.log('Connected values:',await evaluate(`(async () => {
        const cases=[['system_prompt','PrimitiveStringMultiline','Connected system'],['user_prompt','PrimitiveStringMultiline','Connected user'],['top_k','PrimitiveInt',40],['temperature','PrimitiveFloat',.7],['console_output','PrimitiveBoolean',true],['chat_template_kwargs.enable_thinking','PrimitiveBoolean',true],['include_stop_str_in_output','PrimitiveBoolean',true],['chat_template_kwargs','PrimitiveString','{"enable_thinking":false}']];
        const sources=[];
        for(const [name,type,value] of cases) {
            const source=LiteGraph.createNode(type);rmApp.graph.add(source);source.widgets.find(w=>w.name==='value').value=value;
            if(!source.connect(0,rmNode,rmNode.inputs.findIndex(i=>i.name===name)))throw new Error('Connection rejected: '+name);
            sources.push([name,source]);
        }
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const prompt=await rmApp.graphToPrompt(),inputs=prompt.output[String(rmNode.id)].inputs;
        if(Object.keys(inputs).some(n=>n.startsWith('rm_row_')))throw new Error('UI rows leaked into execution');
        for(const [name,source] of sources) {
            if(String(inputs[name]?.[0])!==String(source.id))throw new Error('Missing link: '+name);
            if(!control(name).disabled || !row(name).isConnected || row(name).getBoundingClientRect().height<10)throw new Error('Connected row disappeared: '+name);
        }
        checkAlignment();
        window.savedRM=rmNode.serialize();
        const copy=LiteGraph.createNode('RM_LLM');copy.configure(savedRM);rmApp.graph.add(copy);copy.pos=[1100,200];
        window.rmCopy=copy;
        for(const [name,source] of sources) {rmNode.disconnectInput(rmNode.inputs.findIndex(i=>i.name===name));rmApp.graph.remove(source);}
        return {typedLinks:cases.length,connectedRowsVisible:true,UIRowsExcluded:true};
    })()`));
    await until("rmCopy.widgets.some(w=>w.name==='rm_row_top_k')");
    console.log('Reload:',await evaluate(`(() => {
        const label=rmCopy.widgets.find(w=>w.name==='rm_row_top_k');
        if(rmCopy.inputs.find(i=>i.name==='top_k').widget.name!==label.name)throw new Error('Reload lost row binding');
        if(rmCopy.widgets.find(w=>w.name==='model_name').value!=='AEON-7/DFlash-Qwen3.5-27B-Uncensored')throw new Error('Reload lost model');
        rmApp.graph.remove(rmCopy);return {rowBindings:true,modelPreserved:true};
    })()`));
    console.log('Queue and validation:',await evaluate(`(async () => {
        const api=window.comfyAPI.api.api,original=api.fetchApi,observed=[];
        api.fetchApi=async function(route,options){
            if(String(route)==='/prompt') {const body=JSON.parse(options.body);observed.push(body);return new Response(JSON.stringify({prompt_id:'synthetic-not-queued',number:0,node_errors:{}}),{status:200,headers:{'Content-Type':'application/json'}});}
            return original.call(this,route,options);
        };
        try {
            const field=control('top_k');field.value='.95';field.dispatchEvent(new Event('input'));
            let error='';try {await api.queuePrompt(0,await rmApp.graphToPrompt());}catch(e){error=e.message;}
            if(!error.includes('whole number')||observed.length)throw new Error('Invalid integer not rejected');
            field.value='40';await api.queuePrompt(0,await rmApp.graphToPrompt());
            if(JSON.parse(observed.at(-1).prompt[String(rmNode.id)].inputs.parameters_json).top_k!==40)throw new Error('Setting not sent');
            field.value='';field.dispatchEvent(new Event('input'));
            await api.queuePrompt(0,await rmApp.graphToPrompt());
            if(Object.hasOwn(JSON.parse(observed.at(-1).prompt[String(rmNode.id)].inputs.parameters_json),'top_k'))throw new Error('Blank value sent');
            control('credential_source').value='Masked session key';control('credential_source').dispatchEvent(new Event('change'));
            const keyRow=rmNode.widgets.find(w=>w.element?.querySelector('input[type=password]')).element;
            keyRow.querySelector('input').value='rm-synthetic-row-secret';
            [...keyRow.querySelectorAll('button')].find(b=>b.textContent==='Use key').click();
            await new Promise(r=>setTimeout(r,500));
            await api.queuePrompt(0,await rmApp.graphToPrompt());
            const body=observed.at(-1),ticket=body.prompt[String(rmNode.id)].inputs.key_ticket;
            if(!ticket || JSON.stringify(body).includes('rm-synthetic-row-secret') || JSON.stringify(rmApp.graph.serialize()).includes('rm-synthetic-row-secret'))throw new Error('Credential serialization failed');
            if(JSON.stringify(body.extra_data?.extra_pnginfo).includes(ticket))throw new Error('Ticket saved in workflow');
            [...keyRow.querySelectorAll('button')].find(b=>b.textContent==='Clear key').click();
            return {integerValidation:true,blankDefaults:true,maskedKeyProtected:true,noGenerationSubmitted:true};
        }finally{api.fetchApi=original;}
    })()`));
    await evaluate("rmApp.canvas.ds.scale=.8;rmApp.canvas.ds.offset=[0,0];rmApp.graph.setDirtyCanvas(true,true)");
    await new Promise(r=>setTimeout(r,300));
    console.log('Console switch:',await evaluate(`(async () => {
        const toggle=control('console_output');
        if(toggle.type!=='checkbox' || toggle.getAttribute('role')!=='switch' || toggle.checked)throw new Error('Console switch should default Off');
        if(rmNode.widgets.at(-1).name!=='rm_row_console_output')throw new Error('Console switch is not at bottom');
        for(const enabled of [true,false]) {
            toggle.checked=enabled;toggle.dispatchEvent(new Event('change'));
            const prompt=await rmApp.graphToPrompt();
            if(prompt.output[String(rmNode.id)].inputs.console_output!==enabled)throw new Error('Boolean not serialized');
            const copy=LiteGraph.createNode('RM_LLM');copy.configure(rmNode.serialize());
            if(copy.widgets.find(w=>w.name==='console_output').value!==enabled)throw new Error('Switch not restored');
        }
        return {bottomPosition:true,defaultOff:true,onOffSerialized:true,savedValueRestored:true};
    })()`));
    console.log('Discrete chat-template controls:', await evaluate(`(async () => {
        const read=()=>JSON.parse(rmNode.widgets.find(w=>w.name==='parameters_json').value);
        const thinking=control('chat_template_kwargs.enable_thinking'),raw=control('chat_template_kwargs');
        if(!thinking || rmNode.inputs.find(i=>i.name==='chat_template_kwargs.enable_thinking')?.type!=='BOOLEAN')throw new Error('Missing typed thinking input');
        raw.value='{"custom_setting":7,"thinking":false}';raw.dispatchEvent(new Event('input'));
        if(thinking.value!=='false')throw new Error('Thinking alias did not synchronize control');
        thinking.value='true';thinking.dispatchEvent(new Event('change'));
        if(read().chat_template_kwargs.enable_thinking!==true || read().chat_template_kwargs.custom_setting!==7 || Object.hasOwn(read().chat_template_kwargs,'thinking'))throw new Error('Nested edit lost fields or left conflicting alias');
        const prompt=await rmApp.graphToPrompt();
        const data=JSON.parse(prompt.output[String(rmNode.id)].inputs.parameters_json);
        if(data.chat_template_kwargs.enable_thinking!==true || Object.hasOwn(data,'chat_template_kwargs.enable_thinking'))throw new Error('Nested option serialized at wrong level');
        raw.value='{"enable_thinking":false,"custom_setting":8}';raw.dispatchEvent(new Event('input'));
        if(thinking.value!=='false')throw new Error('Raw JSON did not synchronize discrete control');
        thinking.value='';thinking.dispatchEvent(new Event('change'));
        if(Object.hasOwn(read().chat_template_kwargs,'enable_thinking') || read().chat_template_kwargs.custom_setting!==8)throw new Error('Provider default did not omit only selected field');
        rmNode.widgets.find(w=>w.name==='parameters_json').value='{}';
        rmNode.widgets.find(w=>w.name==='model_name').value='llmfan46/gemma-4-31B-it-uncensored-heretic';rmNode.onConfigure({});
        return {typedSocket:true,nestedSerialization:true,rawJSONSync:true,unknownJSONPreserved:true,defaultOmitted:true};
    })()`));
    await until("!!control('chat_template_kwargs.preserve_thinking')?.isConnected");
    console.log('Gemma template:',await evaluate(`(() => {
        if(!control('chat_template_kwargs.enable_thinking')?.title.includes('Selected model'))throw new Error('Missing model template evidence');
        if(control('chat_template_kwargs.thinking_budget'))throw new Error('Undocumented budget exposed');
        return {thinking:true,preserveThinking:true,unsupportedBudgetHidden:true};
    })()`));
    console.log('Collapse preserves connections:', await evaluate(`(async () => {
        const source=LiteGraph.createNode('PrimitiveInt');rmApp.graph.add(source);source.pos=[-10000,-10000];
        source.widgets.find(w=>w.name==='value').value=40;
        source.connect(0,rmNode,rmNode.inputs.findIndex(i=>i.name==='top_k'));
        const before=JSON.stringify((await rmApp.graphToPrompt()).output[String(rmNode.id)].inputs);
        row('heading_advanced').querySelector('button').click();
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const w=rmNode.widgets.find(w=>w.name==='rm_row_top_k');
        if(w.hidden || !w.rmCompact || w.computedHeight>25)throw new Error('Connected input not compact');
        checkAlignment();
        const after=JSON.stringify((await rmApp.graphToPrompt()).output[String(rmNode.id)].inputs);
        if(before!==after)throw new Error('Collapse changed execution inputs');
        if(rmNode.serialize().properties.rm_llm_sections.advanced!==false)throw new Error('Fold state not saved');
        rmNode.disconnectInput(rmNode.inputs.findIndex(i=>i.name==='top_k'));rmApp.graph.remove(source);
        if(!w.hidden)throw new Error('Disconnected folded input left visible');
        row('heading_standard').querySelector('button').click();
        if(rmNode.widgets.filter(w=>w.name.startsWith('rm_row_')&&!w.hidden).length!==2)throw new Error('Standard did not fold');
        row('heading_standard').querySelector('button').click();
        rmNode.pos=[250,140];rmApp.canvas.ds.scale=1;rmApp.canvas.ds.offset=[0,0];rmApp.graph.setDirtyCanvas(true,true);
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        return {linksPreserved:true,inputsUnchanged:true,compactLinkedLabels:true,foldStateSaved:true,standardFolds:true};
    })()`));
    const screenshot=await cdp("Page.captureScreenshot",{format:"png"});
    await writeFile(new URL('./rm-llm-rows.png',import.meta.url),Buffer.from(screenshot.data,'base64'));
    console.log('Errors:',exceptions.filter(e=>JSON.stringify(e).includes('rm_llm')));
} finally {socket.close();}
