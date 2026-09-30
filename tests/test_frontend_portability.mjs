// Renderer-contract regression tests; no browser or provider requests.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../web/rm_llm.js', import.meta.url), 'utf8');
const document = { createElement: () => ({}), head: { append() {} } };
const context = vm.createContext({ document, app: { registerExtension() {} }, console });
vm.runInContext(source.replace(/^import .*;\r?\n/gm, ''), context);
const run = expression => vm.runInContext(expression, context);

run(`
globalThis.node = {
    properties: {}, inputs: [{ name: 'system_prompt', link: null }],
    widgets: [{ name: 'provider', value: 'Featherless', serialize: true }],
    size: [500, 400], graph: { setDirtyCanvas() {} },
    setSize(size) { this.size = size; }, computeSize() { return [500, 300]; },
    getInputPos() { return [10, 20]; }, drawSlots() {},
};
globalThis.state = { node, v2: true, rows: new Map(), parameterRows: new Set(),
    status: { classList: { contains: () => false } } };
for (const name of ['model_heading','section_3','heading_model','heading_standard','heading_advanced','system_prompt']) {
    const button = { setAttribute() {} };
    const row = { name: 'rm_row_' + name, options: {getMinHeight: () => 58},
        element: { hidden: false, style: {}, dataset: {}, classList: {toggle() {}}, querySelector: () => button } };
    state.rows.set(name, row); node.widgets.push(row);
}
layoutSections(state);
`);
assert.equal(run(`state.rows.get('system_prompt').hidden`), true, 'Canvas sees folded field');
assert.equal(run(`state.rows.get('system_prompt').options.hidden`), true, 'Vue sees folded field');
assert.equal(run(`state.rows.get('system_prompt').element.hidden`), true, 'DOM agrees');
assert.equal(run(`state.rows.get('section_3').hidden`), false, 'Limits remain visible');
assert.equal(run(`state.rows.get('model_heading').hidden`), false, 'Model heading remains visible');
assert.equal(run(`node.widgets[0].name`), 'provider', 'Backing serialization order unchanged');
run(`node.properties.rm_llm_sections.standard = true; layoutSections(state);`);
assert.equal(run(`state.rows.get('system_prompt').options.hidden`), false, 'Vue section expands');
assert.equal(run(`node.inputs[0].alwaysVisible`), true, 'Visible field socket stays visible');
run(`node.inputs[0].link = 12; node.properties.rm_llm_sections.standard = false; layoutSections(state);`);
assert.equal(run(`state.rows.get('system_prompt').options.hidden`), false, 'Connected field preserved');
assert.equal(run(`state.rows.get('system_prompt').rmCompact`), true, 'Connected folded field is compact');
assert.equal(run(`node.inputs[0].link`), 12, 'Connection preserved');
run(`globalThis.draw = node.drawSlots; installSectionSlots(state);`);
assert.equal(run(`node.drawSlots === draw`), true, 'Native slot renderer untouched');
run(`node.inputs[0].link = null; layoutSections(state);`);
assert.equal(run(`Number.isNaN(node.getInputPos(0)[0])`), true, 'Folded socket cannot intercept clicks');
run(`node.properties.rm_llm_sections.standard = true; layoutSections(state);`);
assert.equal(run(`node.getInputPos(0)[0]`), 10, 'Expanded socket uses native position');
assert.equal(source.includes('_concreteInputs'), false, 'No private slot-array mutation');
assert.equal(source.includes('_widgetSlotsDirty'), false, 'No private layout flag');
assert.equal(source.includes('onDrawForeground'), false, 'Header independent of canvas renderer');
console.log('Frontend portability contracts passed (not a visual browser test).');
