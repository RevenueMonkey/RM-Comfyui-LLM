// Offline UI logic regression; no browser, server, or provider calls.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../web/rm_llm.js', import.meta.url), 'utf8');
const context = vm.createContext({
    document: { createElement: () => ({}), head: { append() {} } },
    app: { registerExtension() {} }, console,
});
vm.runInContext(source.replace(/^import .*;\r?\n/gm, ''), context);
const run = text => vm.runInContext(text, context);
run(`
globalThis.requests = [];
globalThis.node = {
    widgets: [{name:'provider',value:'OpenRouter'}, {name:'model_name',value:'old/model'}],
    inputs: [{name:'provider',link:1}, {name:'model_name',link:2}, {name:'reasoning',link:99}],
    addInput(name,type) { this.inputs.push({name,type,link:null}); },
    removeInput(index) { this.inputs.splice(index,1); },
};
globalThis.state = {node, v2:true, revision:0, caps:null,
    validators:new Map(), invalid:new Map(), parameterNames:new Set(['reasoning']),
    controls:{replaceChildren(){}}, capInfo:{}, lastRefreshed:{},
};
bindRows = () => {};
mountParameterRows = () => {};
renderControls = () => {};
syncConnectedControls = () => {};
layoutSections = () => {};
note = (s,text) => { s.notice=text; };
call = async (action,selection) => {
    requests.push({action,...selection});
    return {provider:selection.provider, parameters:{temperature:{type:'number'},top_p:{type:'number'}}, input_modalities:['text']};
};
`);
assert.equal(run('modelSelection(state).model'), undefined, 'Never use stale dropdown for a connection');
await run('loadCapabilities(state)');
assert.equal(run('requests.length'), 0, 'Do not query capabilities of the wrong model');
assert.match(run('state.capInfo.textContent'), /Awaiting connected model/);
assert.equal(run("node.inputs.find(i=>i.name==='reasoning').link"), 99, 'Preserve existing wires while unresolved');
run("receiveModel(state,{provider:'OpenRouter',model:'synthetic/kimi'})");
await run('Promise.resolve()');
assert.equal(run('requests.at(-1).model'), 'synthetic/kimi');
assert.equal(run("node.inputs.find(i=>i.name==='temperature').type"), 'FLOAT');
assert.equal(run("node.inputs.find(i=>i.name==='top_p').type"), 'FLOAT');
assert.equal(run("node.inputs.find(i=>i.name==='reasoning').link"), 99, 'Unsupported wired inputs stay connected');
assert.equal(run("value(node,'model_name')"), 'old/model', 'Do not overwrite saved dropdown');
run("receiveModel(state,{provider:'OpenRouter',model:'synthetic/kimi'})");
assert.equal(run('requests.length'), 1, 'Cached UI metadata does not repeat discovery');
run("receiveModel(state,{provider:'Featherless',model:'synthetic/next'})");
await run('Promise.resolve()');
assert.equal(run('requests.at(-1).provider'), 'Featherless');
assert.equal(run('requests.at(-1).model'), 'synthetic/next', 'Next loop pass refreshes model');
run("node.inputs.find(i=>i.name==='model_name').link=null; node.inputs.find(i=>i.name==='provider').link=null;");
await run('loadCapabilities(state)');
assert.equal(run('requests.at(-1).model'), 'old/model', 'Disconnect restores local selection');
run(`
node.inputs.find(i=>i.name==='model_name').link=2;
node.inputs.find(i=>i.name==='provider').link=1;
globalThis.pending=[];
call=(action,selection)=>new Promise(resolve=>pending.push({selection,resolve}));
receiveModel(state,{provider:'OpenRouter',model:'synthetic/slow'});
receiveModel(state,{provider:'OpenRouter',model:'synthetic/fast'});
pending[1].resolve({provider:'OpenRouter',parameters:{top_p:{type:'number'}},input_modalities:['text'],tag:'fast'});
`);
await run('Promise.resolve()');
run("pending[0].resolve({provider:'OpenRouter',parameters:{},input_modalities:['text'],tag:'slow'})");
await run('Promise.resolve()');
assert.equal(run('state.caps.tag'), 'fast', 'Ignore stale asynchronous capability responses');
assert.equal(run("executionNode({getNodeById:id=>id==='271'?{subgraph:{getNodeById:id=>id==='445'?node:null}}:null},'271:445')===node"), true, 'Subgraph execution IDs resolve');
assert.equal(run("executionNode({getNodeById:()=>null},'271:445')"), undefined, 'Removed nodes ignored');
console.log('Connected-model UI regression checks passed (not a visual browser test).');
