/* Solar Window 0.1.2 — dependency-free Home Assistant card. */
export const escapeHtml = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function dateAdd(key, count) {
  const d = new Date(`${key}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + count); return d.toISOString().slice(0,10);
}
export function monday(key) {
  const d = new Date(`${key}T12:00:00Z`); return dateAdd(key, -(d.getUTCDay()+6)%7);
}
export function localParts(iso, tz) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone:tz, year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(iso)).map(x=>[x.type,x.value]));
  return {date:`${p.year}-${p.month}-${p.day}`, minutes:Number(p.hour)*60+Number(p.minute), time:`${p.hour}:${p.minute}`};
}
export function parseCsv(text) {
  const rows=[]; let row=[], field='', quoted=false;
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(c==='"') { if(quoted && text[i+1]==='"') {field+='"';i++;} else quoted=!quoted; }
    else if(c===',' && !quoted) {row.push(field);field='';}
    else if(c==='\n' && !quoted) {row.push(field.replace(/\r$/,''));if(row.some(Boolean))rows.push(row);row=[];field='';}
    else field+=c;
  }
  if(quoted) throw new Error('Unterminated CSV quote');
  if(field || row.length) {row.push(field.replace(/\r$/,''));rows.push(row);}
  return rows;
}
export function historyToDays(text, tz, selectedEntity) {
  const [header,...rows]=parseCsv(text.replace(/^\uFEFF/,''));
  if(!header) throw new Error('CSV is empty');
  const e=header.indexOf('entity_id'), s=header.indexOf('state'), t=header.indexOf('last_changed');
  if([e,s,t].some(x=>x<0)) throw new Error('CSV requires entity_id, state and last_changed columns');
  const entities=[...new Set(rows.map(r=>r[e]))];
  if(!selectedEntity && entities.length!==1) throw new Error('Import a CSV containing one solar on/off entity');
  const events=rows.filter(r=>r[e]===(selectedEntity||entities[0])).map(r=>{if(!/(Z|[+-]\d{2}:?\d{2})$/i.test(r[t]))throw new Error('CSV timestamps must include a timezone');return {state:r[s],at:new Date(r[t])};});
  if(events.some(v=>!Number.isFinite(v.at.valueOf()))) throw new Error('Invalid CSV timestamp');
  events.sort((a,b)=>a.at-b.at);
  const days=new Map();let open=null, prior=null;
  for(const event of events) {
    if(!['on','off'].includes(event.state)) {if(open) days.get(open).flags.push('recording_gap');open=null;prior=null;continue;}
    if(event.state===prior) continue;
    prior=event.state;
    const key=localParts(event.at.toISOString(),tz).date;
    if(event.state==='on') {
      if(open && open!==key) {days.get(open).flags.push('recording_gap');open=null;}
      const row=days.get(key)||{date:key,start:event.at.toISOString(),finish:null,source:'import',flags:['legacy_switch']};
      if(days.has(key)) row.flags.push('interrupted');
      row.finish=null;days.set(key,row);open=key;
    } else if(open) {
      const row=days.get(open);
      if(event.at-new Date(row.start)>26*3600000) row.flags.push('recording_gap');
      else row.finish=event.at.toISOString();
      open=null;
    }
  }
  return [...days.values()].map(r=>({...r,flags:[...new Set(r.flags)]}));
}
const months=['January','February','March','April','May','June','July','August','September','October','November','December'];

class SolarWindowCard extends HTMLElement {
  constructor() {super();this.attachShadow({mode:'open'});this._mode='year';this._rows=[];this._year=new Date().getFullYear();this._month=new Date().getMonth()+1;this._week=monday(new Date().toISOString().slice(0,10));this._message='';this._request=0;}
  setConfig(config) {if(this._config?.entry_id!==config.entry_id)this._entry=null;this._config=config;this._mode=config.view||'year';if(!['year','month','week'].includes(this._mode))throw new Error('view must be year, month or week');this.render();if(this._hass)this.load();}
  set hass(value) {
    const first=!this._hass;this._hass=value;
    if(first) {const local=localParts(new Date().toISOString(),value.config.time_zone);this._year=Number(local.date.slice(0,4));this._month=Number(local.date.slice(5,7));this._week=monday(local.date);this.load();}
  }
  connectedCallback() {if(!this._timer)this._timer=setInterval(()=>this.load(),60000);if(this._hass)this.load();}
  disconnectedCallback() {clearInterval(this._timer);this._timer=null;}
  getCardSize() {return this._mode==='month'?12:7;}
  static getStubConfig() {return {type:'custom:solar-window-card',view:'year'};}
  static getConfigElement() {return document.createElement('solar-window-card-editor');}
  async load() {
    if(!this._hass||!this._config)return;
    const request=++this._request;
    try {
      if(!this._entry) {
        const data=await this._hass.callWS({type:'solar_window/records'});
        if(request!==this._request)return;
        if(this._config.entry_id)this._entry=this._config.entry_id;
        else if(data.entries.length===1)this._entry=data.entries[0].entry_id;
        else throw new Error(data.entries.length?'Choose an installation in the card visual editor':'Add the Solar Window integration first');
      }
      // A week crossing New Year needs both years.
      const years=[this._year];
      if(this._mode==='week') {years.splice(0,1,...new Set([Number(this._week.slice(0,4)),Number(dateAdd(this._week,6).slice(0,4))]));}
      const data=await Promise.all(years.map(year=>this._hass.callWS({type:'solar_window/records',entry_id:this._entry,year})));
      if(request!==this._request)return;
      this._rows=data.flatMap(x=>x.days);this._tz=data[0].timezone;this._years=data[0].years;this._lastSeen=data[0].last_seen;this._error='';
    } catch(e) {if(request!==this._request)return;this._error=e.message||String(e);}
    this.render();
  }
  minutes(row,end=false) {
    const value=end?row.finish:row.start;
    if(!value)return end ? (row.date===localParts(new Date().toISOString(),this._tz).date ? localParts(new Date().toISOString(),this._tz).minutes : null) : null;
    const part=localParts(value,this._tz);
    return end && part.date>row.date?1440:part.minutes;
  }
  caption(row) {
    const first=localParts(row.start,this._tz).time;
    const last=row.finish?localParts(row.finish,this._tz).time:(row.date===localParts(new Date().toISOString(),this._tz).date?'ongoing':'end unknown');
    return `${row.date} · ${first} – ${last}${row.flags.length?' · '+row.flags.join(', ').replaceAll('_',' '):''}`;
  }
  yearChart() {
    const total=(new Date(Date.UTC(this._year+1,0,1))-new Date(Date.UTC(this._year,0,1)))/86400000;
    const x=key=>52+(new Date(`${key}T00:00:00Z`)-new Date(Date.UTC(this._year,0,1)))/86400000/total*660;
    const y=m=>20+m/1440*300;
    let svg='';
    for(const hour of [0,6,12,18,24]) svg+=`<line class="grid" x1="52" x2="712" y1="${y(hour*60)}" y2="${y(hour*60)}"/><text x="42" y="${y(hour*60)+4}" text-anchor="end">${String(hour).padStart(2,'0')}:00</text>`;
    for(const row of this._rows) {
      if(Number(row.date.slice(0,4))!==this._year)continue;
      const start=this.minutes(row), finish=this.minutes(row,true);
      if(start===null)continue;
      svg+=`<rect data-month="${Number(row.date.slice(5,7))}" class="solar ${row.source==='statistics'?'approx':''}" x="${x(row.date)}" y="${y(start)}" width="${Math.max(1,660/total)}" height="${Math.max(2,y(finish??start)-y(start))}"><title>${escapeHtml(this.caption(row))}</title></rect>`;
      if(row.flags.includes('recording_gap')) svg+=`<circle class="gap" cx="${x(row.date)}" cy="${y(start)}" r="2.4"/>`;
    }
    for(let m=1;m<=12;m++) {
      const key=`${this._year}-${String(m).padStart(2,'0')}-01`, next=m===12?`${this._year+1}-01-01`:`${this._year}-${String(m+1).padStart(2,'0')}-01`;
      svg+=`<line class="grid" x1="${x(key)}" x2="${x(key)}" y1="20" y2="320"/><g class="month-link" data-month="${m}" role="button" tabindex="0" aria-label="Open ${months[m-1]}"><rect x="${x(key)}" y="20" width="${x(next)-x(key)}" height="328" fill="transparent" pointer-events="none"/><text x="${(x(key)+x(next))/2}" y="344" text-anchor="middle">${months[m-1].slice(0,3)}</text></g>`;
    }
    return `<svg viewBox="0 0 730 360" role="img" aria-label="Daily solar production windows for ${this._year}; click a month to explore">${svg}</svg>`;
  }
  dayRows() {
    let keys=[];
    if(this._mode==='week')for(let i=0;i<7;i++)keys.push(dateAdd(this._week,i));
    else {const count=new Date(Date.UTC(this._year,this._month,0)).getUTCDate();for(let i=1;i<=count;i++)keys.push(`${this._year}-${String(this._month).padStart(2,'0')}-${String(i).padStart(2,'0')}`);}
    let html='<div class="axis"><span></span><div><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div></div>';
    let priorWeek='';
    for(const key of keys) {
      const week=monday(key);
      if(this._mode==='month'&&week!==priorWeek)html+=`<button class="week-heading" data-week="${week}">Week of ${this.displayDate(week)} <span>View days →</span></button>`;
      priorWeek=week;
      const row=this._rows.find(r=>r.date===key);
      const label=new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${key}T12:00Z`));
      if(!row) {html+=`<div class="day"><span>${label}</span><div class="track empty">No recording</div></div>`;continue;}
      const start=this.minutes(row), end=this.minutes(row,true);
      const intervals=this._mode==='week'&&row.source==='live'?row.intervals:[{start:row.start,end:row.finish}];
      let bars='';
      for(const interval of intervals) {
        const from=localParts(interval.start,this._tz).minutes;
        const part=interval.end?localParts(interval.end,this._tz):null;
        const to=part?(part.date>key?1440:part.minutes):end;
        bars+=`<span class="bar ${row.source==='statistics'?'approx':''} ${!interval.end?'open':''}" style="left:${from/14.4}%;width:${Math.max(.3,((to??from)-from)/14.4)}%"></span>`;
      }
      html+=`<div class="day" title="${escapeHtml(this.caption(row))}"><span>${label}</span><div class="track">${bars}</div></div><div class="times">${escapeHtml(this.caption(row).split(' · ').slice(1).join(' · '))}</div>`;
    }
    return `<div class="daily">${html}</div>`;
  }
  displayDate(key) {return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(`${key}T12:00Z`));}
  async navigate(action) {
    if(action==='year'||action==='month'||action==='week'){if(action==='week'&&this._mode!=='week')this._week=monday(`${this._year}-${String(this._month).padStart(2,'0')}-01`);if(action==='month'&&this._mode==='week'){this._year=Number(this._week.slice(0,4));this._month=Number(this._week.slice(5,7));}this._mode=action;}
    else {const n=action==='prev'?-1:1;if(this._mode==='year')this._year+=n;else if(this._mode==='month'){const d=new Date(Date.UTC(this._year,this._month-1+n,1));this._year=d.getUTCFullYear();this._month=d.getUTCMonth()+1;}else {this._week=dateAdd(this._week,n*7);this._year=Number(this._week.slice(0,4));this._month=Number(this._week.slice(5,7));}}
    this._year=Math.max(1970,Math.min(2100,this._year));await this.load();
  }
  render() {
    if(!this._config)return;
    const title=this._mode==='year'?String(this._year):this._mode==='month'?`${months[this._month-1]} ${this._year}`:`${this.displayDate(this._week)} – ${this.displayDate(dateAdd(this._week,6))} ${this._week.slice(0,4)}`;
    const observed=this._rows.filter(r=>this._mode==='year'||(this._mode==='month'?r.date.startsWith(`${this._year}-${String(this._month).padStart(2,'0')}`):r.date>=this._week&&r.date<=dateAdd(this._week,6)));
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;font-family:var(--primary-font-family,system-ui);color:var(--primary-text-color,#e7edf2)}ha-card{display:block;background:var(--ha-card-background,var(--card-background-color,#17212b));border-radius:var(--ha-card-border-radius,20px);border:1px solid var(--divider-color,#2e3b47);padding:22px;overflow:hidden}*{box-sizing:border-box}h2{font-size:20px;margin:0}p{color:var(--secondary-text-color,#9baab7);font-size:13px;line-height:1.5;margin:7px 0}.top{display:flex;justify-content:space-between;align-items:center;gap:12px}.sun{color:#ffbf5e;font-size:25px}.modes{display:flex;gap:5px;margin:18px 0}button,select,.file-label{font:inherit;background:transparent;border:1px solid var(--divider-color,#394858);color:inherit;border-radius:9px;padding:7px 12px;cursor:pointer;font-size:13px}button:hover,.file-label:hover{background:#ffffff10}button.active{background:#ffbf5e;color:#202833;border-color:#ffbf5e}.period{display:flex;gap:10px;align-items:center;justify-content:space-between;margin-bottom:14px}.period strong{font-size:16px}.period select{background:var(--card-background-color,#17212b)}svg{width:100%;height:auto;display:block}svg text{fill:var(--secondary-text-color,#9baab7);font-size:11px}.grid{stroke:var(--divider-color,#35424f);stroke-width:.6}.solar,.bar{fill:#ffbf5e;background:#ffbf5e}.solar.approx{opacity:.5}.gap{fill:#ff7d81}.month-link{cursor:pointer}.month-link:hover rect{fill:#ffffff0b}.month-link:focus{outline:2px solid #ffbf5e}.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color,#9baab7);margin-top:12px}.legend i{display:inline-block;width:9px;height:9px;border-radius:3px;background:#ffbf5e;margin-right:5px}.legend .muted{opacity:.5}.legend .red{background:#ff7d81}.summary{display:flex;gap:28px;border-top:1px solid var(--divider-color,#35424f);margin-top:18px;padding-top:14px}.summary strong{font-size:20px;display:block}.summary small{color:var(--secondary-text-color,#9baab7)}.axis,.day{display:grid;grid-template-columns:65px 1fr;gap:8px}.axis{font-size:10px;color:var(--secondary-text-color,#9baab7);margin:10px 0}.axis div{display:flex;justify-content:space-between}.day{align-items:center;min-height:24px;font-size:12px}.track{position:relative;height:18px;border-radius:4px;background:repeating-linear-gradient(90deg,#ffffff04 0, #ffffff04 calc(25% - 1px),#ffffff18 calc(25% - 1px),#ffffff18 25%)}.bar{position:absolute;top:3px;height:12px;border-radius:3px}.bar.approx{opacity:.5}.bar.open{background:repeating-linear-gradient(90deg,#ffbf5e 0,#ffbf5e 4px,#ffbf5e44 4px,#ffbf5e44 7px)}.empty{color:var(--secondary-text-color,#9baab7);font-size:10px;text-align:center;line-height:18px}.times{font-size:10px;color:var(--secondary-text-color,#9baab7);margin:1px 0 9px 73px}.week-heading{width:100%;text-align:left;margin:12px 0 6px;font-size:12px}.week-heading span{float:right;color:var(--secondary-text-color,#9baab7)}details{margin-top:18px;border-top:1px solid var(--divider-color,#35424f);padding-top:12px;font-size:12px}summary{cursor:pointer;color:var(--secondary-text-color,#9baab7)}.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.notice{white-space:pre-wrap;color:var(--secondary-text-color,#9baab7)}.error{color:#ff7d81}.blank{padding:40px 15px;text-align:center}button:disabled{opacity:.5;cursor:wait}@media(max-width:450px){ha-card{padding:14px}.summary{gap:18px}.times{font-size:9px}}
    </style><ha-card><div class="top"><h2>${escapeHtml(this._config.title||'Solar window')}</h2><span class="sun" aria-hidden="true">☀</span></div><p>When your panels produce · ${escapeHtml(this._tz||this._hass?.config.time_zone||'')}</p>
    <div class="modes">${['year','month','week'].map(v=>`<button data-action="${v}" class="${v===this._mode?'active':''}">${v[0].toUpperCase()+v.slice(1)}</button>`).join('')}</div>
    <div class="period"><button data-action="prev" aria-label="Previous period">←</button><strong>${escapeHtml(title)}</strong><button data-action="next" aria-label="Next period">→</button></div>
    ${this._error?`<p class="error">${escapeHtml(this._error)}</p>`:this._tz?(this._mode==='year'?this.yearChart():this.dayRows()):'<div class="blank">Loading solar records…</div>'}
    ${!observed.length&&this._tz?'<p>No recordings in this period. Import history or backfill Energy data below.</p>':''}
    <div class="legend"><span><i></i>Recorded window</span><span><i class="muted"></i>Hourly estimate</span><span><i class="red"></i>Recording gap</span></div>
    <div class="summary"><div><strong>${observed.length}</strong><small>Days recorded</small></div><div><strong>${observed.filter(r=>r.source==='statistics').length}</strong><small>Approximate days</small></div><div><strong>${observed.filter(r=>r.flags.includes('recording_gap')).length}</strong><small>Days with gaps</small></div></div>
    <details><summary>History & data</summary><p>Imports keep the original switch observations. Hourly backfill is approximate and will not replace imported or live records.</p><div class="tools"><label class="file-label">Import CSV / JSON<input type="file" accept=".csv,.json" hidden></label><button id="backfill">Backfill ${this._year}</button><button id="export">Export ${this._year}</button></div><p class="notice">${escapeHtml(this._message)}</p><p>Power thresholds and confirmation times are configured in the integration. This shows production timing, not energy yield.</p></details></ha-card>`;
    this.shadowRoot.querySelectorAll('[data-action]').forEach(el=>el.onclick=()=>this.navigate(el.dataset.action));
    this.shadowRoot.querySelectorAll('[data-month]').forEach(el=>{const action=()=>{this._month=Number(el.dataset.month);this._mode='month';this.load();};el.onclick=action;el.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();action();}};});
    this.shadowRoot.querySelectorAll('[data-week]').forEach(el=>el.onclick=()=>{this._week=el.dataset.week;this._mode='week';this.load();});
    this.shadowRoot.querySelector('input').onchange=e=>this.importFile(e.target.files[0]);
    this.shadowRoot.querySelector('#backfill').onclick=()=>this.backfill();
    this.shadowRoot.querySelector('#export').onclick=()=>this.exportFile();
  }
  async importFile(file) {
    if(!file||!this._entry)return;
    try {
      const text=await file.text();const data=file.name.toLowerCase().endsWith('.csv')?historyToDays(text,this._tz):JSON.parse(text);
      const days=Array.isArray(data)?data:data.days;
      if(!Array.isArray(days))throw new Error('JSON must contain a days array');
      const imported=days.map(r=>({...r,source:r.source==='statistics'?'statistics':'import'}));
      const result=await this._hass.callWS({type:'solar_window/import',entry_id:this._entry,days:imported});
      this._message=`Imported ${result.imported} days. Existing records of equal or higher quality were kept.`;
      if(days.length){this._year=Number(days[0].date.slice(0,4));this._month=Number(days[0].date.slice(5,7));this._week=monday(days[0].date);}
    } catch(e) {this._message=`Import failed: ${e.message||String(e)}`;}
    await this.load();
  }
  async backfill() {
    const button=this.shadowRoot.querySelector('#backfill');button.disabled=true;button.textContent='Reading statistics…';
    try {const result=await this._hass.callWS({type:'solar_window/backfill',entry_id:this._entry,year:this._year});this._message=`Added ${result.imported} approximate days (${result.available_days} available).`;}
    catch(e){this._message=`Backfill failed: ${e.message||String(e)}`;}
    await this.load();
  }
  exportFile() {
    const data={version:1,timezone:this._tz,days:this._rows.filter(r=>Number(r.date.slice(0,4))===this._year)};
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download=`solar-window-${this._year}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
class SolarWindowCardEditor extends HTMLElement {
  constructor() {super();this.attachShadow({mode:'open'});this._entries=[];this._config={};}
  setConfig(config) {this._config={...config};this.render();}
  set hass(hass) {
    this._hass=hass;
    if(!this._loading && !this._loaded)this.loadEntries();
  }
  async loadEntries() {
    this._loading=true;
    try {
      const data=await this._hass.callWS({type:'solar_window/records'});
      this._entries=data.entries;this._loaded=true;this._error=null;
    } catch(e) {this._error=e.message||String(e);}
    finally {this._loading=false;this.render();}
  }
  update(key,value) {
    const config={...this._config};
    if(value)config[key]=value;else delete config[key];
    this._config=config;
    this.dispatchEvent(new CustomEvent('config-changed',{detail:{config},bubbles:true,composed:true}));
  }
  render() {
    const config=this._config;
    const entries=[...this._entries];
    if(config.entry_id && !entries.some(entry=>entry.entry_id===config.entry_id))entries.push({entry_id:config.entry_id,title:'Unavailable installation'});
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:var(--primary-text-color)}
      label{display:block;margin:16px 0 6px}input,select{box-sizing:border-box;width:100%;padding:12px;border:1px solid var(--divider-color,#aaa);border-radius:6px;background:var(--card-background-color,#fff);color:inherit;font:inherit}
      p{color:var(--secondary-text-color);font-size:14px}
    </style>
    <label for="title">Title</label><input id="title" placeholder="Solar production window" value="${escapeHtml(config.title||'')}">
    <label for="view">Starting view</label><select id="view">${['year','month','week'].map(view=>`<option value="${view}" ${view===(config.view||'year')?'selected':''}>${view[0].toUpperCase()+view.slice(1)}</option>`).join('')}</select>
    <label for="entry_id">Installation</label><select id="entry_id"><option value="" ${!config.entry_id?'selected':''}>Automatic (single installation)</option>${entries.map(entry=>`<option value="${escapeHtml(entry.entry_id)}" ${entry.entry_id===config.entry_id?'selected':''}>${escapeHtml(entry.title||'Solar Window')}${entries.length>1?' ('+escapeHtml(entry.entry_id.slice(0,8))+')':''}</option>`).join('')}</select>
    <p>${this._error?escapeHtml(this._error):'Choose an installation when more than one is configured.'}</p>`;
    for(const key of ['title','view','entry_id'])this.shadowRoot.querySelector('#'+key).onchange=event=>this.update(key,event.target.value);
  }
}
// Older manual resources can coexist with the automatically versioned module.
if(!customElements.get('solar-window-card'))customElements.define('solar-window-card',SolarWindowCard);
if(!customElements.get('solar-window-card-editor'))customElements.define('solar-window-card-editor',SolarWindowCardEditor);
window.customCards=window.customCards||[];
if(!window.customCards.some(card=>card.type==='solar-window-card'))window.customCards.push({type:'solar-window-card',name:'Solar Window',preview:true,description:'Daily solar production windows with year, month and week drill-down.'});
