import {test} from 'node:test';
import assert from 'node:assert/strict';
class Shadow {
  set innerHTML(value){this.html=value;this.nodes=new Map();}
  get innerHTML(){return this.html;}
  querySelector(key){if(!this.nodes.has(key))this.nodes.set(key,{});return this.nodes.get(key);}
}
globalThis.HTMLElement=class extends EventTarget {attachShadow(){this.shadowRoot=new Shadow();}};
const registry=new Map();
globalThis.customElements={get:name=>registry.get(name),define(name,value){assert.ok(!registry.has(name));registry.set(name,value);}};
globalThis.window={};
globalThis.document={createElement:name=>new (registry.get(name))()};
const url='../custom_components/solar_window/frontend/solar-window-card.js';
await import(url);
const Editor=registry.get('solar-window-card-editor');
test('card picker creates the visual editor with year as the default view',()=>{
  const Card=registry.get('solar-window-card');
  assert.ok(Card.getConfigElement() instanceof Editor);
  assert.equal(Card.getStubConfig().view,'year');
  assert.equal(window.customCards[0].preview,true);
});
test('editor changes preserve custom options and emit dashboard configuration events',()=>{
  const editor=new Editor();editor.setConfig({type:'custom:solar-window-card',title:'Old',entry_id:'a',custom_option:42});
  let event;editor.addEventListener('config-changed',value=>event=value);
  editor.shadowRoot.querySelector('#view').onchange({target:{value:'month'}});
  assert.deepEqual(event.detail.config,{type:'custom:solar-window-card',title:'Old',entry_id:'a',custom_option:42,view:'month'});
  assert.ok(event.bubbles && event.composed);
  editor.shadowRoot.querySelector('#entry_id').onchange({target:{value:''}});
  assert.equal(event.detail.config.entry_id,undefined);
});
test('editor fetches installation choices and safely escapes their labels',async()=>{
  const editor=new Editor();editor.setConfig({title:'<hello>',entry_id:'b',view:'week'});
  let calls=0;editor.hass={callWS:async message=>{calls++;assert.equal(message.type,'solar_window/records');return {entries:[{entry_id:'a',title:'Roof & garage'},{entry_id:'b',title:'<South>'}]};}};
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(editor.shadowRoot.innerHTML,/Roof &amp; garage/);
  assert.match(editor.shadowRoot.innerHTML,/&lt;South&gt;/);
  assert.match(editor.shadowRoot.innerHTML,/value="b" selected/);
  assert.match(editor.shadowRoot.innerHTML,/value="week" selected/);
  editor.hass={callWS(){throw new Error('unnecessary reload');}};
  assert.equal(calls,1);
});
test('failed installation lookup preserves configuration and can retry',async()=>{
  const editor=new Editor();editor.setConfig({entry_id:'missing'});
  editor.hass={callWS:async()=>{throw new Error('Not connected');}};
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(editor.shadowRoot.innerHTML,/Not connected/);
  assert.match(editor.shadowRoot.innerHTML,/value="missing" selected/);
  editor.hass={callWS:async()=>({entries:[{entry_id:'missing',title:'Recovered'}]})};
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(editor.shadowRoot.innerHTML,/Recovered/);
});
test('manual and automatic module URLs coexist without duplicate registrations',async()=>{
  const Card=registry.get('solar-window-card');
  await import(url+'?v=0.1.0');await import(url+'?v=0.1.1');
  assert.equal(registry.get('solar-window-card'),Card);
  assert.equal(registry.size,2);assert.equal(window.customCards.length,1);
});
