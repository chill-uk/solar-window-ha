import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
class Shadow {
  set innerHTML(value){this.html=value;this.nodes=new Map();}
  get innerHTML(){return this.html;}
  querySelector(key){if(!this.nodes.has(key))this.nodes.set(key,{});return this.nodes.get(key);}
  querySelectorAll(key){const attr=key.match(/^\[([^\]]+)\]$/)?.[1];if(!attr)return[];return [...this.html.matchAll(new RegExp(`${attr}="([^\"]+)"`,'g'))].map(m=>({dataset:{[attr.replace('data-','')]:m[1]}}));}
}
globalThis.HTMLElement=class {attachShadow(){this.shadowRoot=new Shadow();}};
let Card;
globalThis.customElements={define(name,card){Card=card;}};
globalThis.window={};
await import('../custom_components/solar_window/frontend/solar-window-card.js');
const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/solar-history.json',import.meta.url),'utf8'));
async function create(mode='year') {
  const card=new Card();card.setConfig({type:'custom:solar-window-card',view:mode});
  card._hass={config:{time_zone:'Europe/Amsterdam'},callWS:async msg=>msg.entry_id?{days:fixture.days.filter(d=>d.date.startsWith(String(msg.year))),timezone:'Europe/Amsterdam',years:[2026]}:{entries:[{entry_id:'test',title:'Test'}]}};
  card._year=2026;card._month=10;card._week='2026-09-28';await card.load();return card;
}
test('year renders only real daily windows and all month navigation labels',async()=>{const card=await create();assert.match(card.shadowRoot.innerHTML,/January/);assert.match(card.shadowRoot.innerHTML,/Daily solar production windows for 2026/);assert.equal((card.shadowRoot.innerHTML.match(/class="solar /g)||[]).length,10);assert.ok(!card.shadowRoot.innerHTML.includes('NaN'));});
test('month groups the full calendar into weeks and shows missing records',async()=>{const card=await create('month');assert.equal((card.shadowRoot.innerHTML.match(/class="day"/g)||[]).length,31);assert.match(card.shadowRoot.innerHTML,/Week of 28 Sep/);assert.match(card.shadowRoot.innerHTML,/No recording/);});
test('week includes seven days across month boundary and observed local times',async()=>{const card=await create('week');assert.equal((card.shadowRoot.innerHTML.match(/class="day"/g)||[]).length,7);assert.match(card.shadowRoot.innerHTML,/08:00 – 18:00/);});
test('period arrows and mode buttons move through the selected period',async()=>{const card=await create('month');await card.navigate('prev');assert.equal(card._month,9);await card.navigate('week');assert.equal(card._week,'2026-08-31');await card.navigate('next');assert.equal(card._week,'2026-09-07');});
test('multiple configured installations require explicit selection',async()=>{const card=await create();card._entry=null;card._hass.callWS=async()=>({entries:[{entry_id:'a'},{entry_id:'b'}]});await card.load();assert.match(card._error,/Set entry_id/);});
