// Execute the real dashboard functions with synthetic responses; no live writes.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('wp-content/mu-plugins/gaia-dashboard.js', 'utf8');
const names = ['asNumber', 'formatMinutesShort', 'sleepStageCards', 'commitCurrentSymptomStateChange',
  'rebuildCurrentSymptomsSummary', 'updateCurrentSymptomsSnapshot', 'upsertCurrentSymptomItem'];
let code = '';
for (const name of names) {
  const start = source.indexOf('  const ' + name + ' =');
  assert(start >= 0, name);
  const end = source.indexOf('\n  const ', start + 1);
  code += source.slice(start, end) + '\n';
}
code += 'globalThis.checked = {' + names.join(',') + '};';
function fixture({ prompt = false, outcome = 'lost-saved', next = 'improving' } = {}) {
  let writes = 0, reads = 0, body;
  const item = { id: 'episode', label: 'Fatigue', current_state: 'ongoing', activity_status: 'active',
    last_interaction_at: '2026-11-07T12:00:00Z', pending_follow_up: prompt ? { id: 'prompt' } : null };
  const state = { ui: {}, authCtx: {token:'synthetic'}, member: {errors:{},currentSymptoms:{items:[item]}} };
  const save = async (token, id, sent) => {
    writes++; body = sent;
    if(outcome !== 'success' && outcome !== 'rejected') throw new Error('HTTP 502: member hub proxy fetch failed');
    if(outcome === 'rejected') return {ok:false,error:'stale update'};
    const saved = {...item,current_state:next,activity_status:next === 'resolved' ? 'resolved' : 'active', last_interaction_at:sent.ts_utc,pending_follow_up:null};
    return {ok:true,data:prompt ? {episode:saved}:saved};
  };
  const context = {
    Date, encodeURIComponent,
    textOrEmpty:v=>v == null ? '' : String(v), maybeArray:v=>Array.isArray(v)?v:[], maybeObject:v=>v && typeof v==='object'?v:null,
    featureValue:(f,...keys)=>keys.map(k=>f[k]).find(v=>v != null),
    cloneJson:v=>JSON.parse(JSON.stringify(v)), normalizeCurrentSymptomState:v=>v || 'new',
    extractEnvelopeData:v=>v?.data, extractCurrentSymptoms:v=>v?.data || v,
    isCurrentSymptomPending:s=>!!s.pending, setCurrentSymptomPending:(s,id,v)=>s.pending=v,
    setCurrentSymptomRowStatus:(s,id,message,isError)=>s.status={message,isError},
    renderMemberHub:()=>{}, refreshCurrentSymptomsInBackground:()=>{}, refreshSymptomGauges:()=>{},
    routeFor:()=>'/synthetic/current', respondCurrentSymptomFollowUp:save, updateCurrentSymptomState:save,
    fetchJson:async (url,token)=> {
      reads++; assert.equal(url,'/synthetic/current/episode'); assert.equal(token,'synthetic');
      if(outcome === 'lost-unavailable') throw new Error('unavailable');
      const saved = {...item, current_state:next, activity_status:next === 'resolved' ? 'resolved' : 'active',
        last_interaction_at: outcome === 'lost-stale' ? item.last_interaction_at : body.ts_utc, pending_follow_up:null};
      if(outcome === 'lost-other-id') saved.id='other';
      if(outcome === 'lost-other-state') saved.current_state='worse';
      return {ok:outcome !== 'lost-error-envelope',data:saved};
    }
  };
  vm.runInNewContext(code,context);
  return {state,item,checked:context.checked,counts:()=>({writes,reads})};
}
(async()=>{
  const {checked}=fixture();
  for(const missing of [0,null,undefined,-1]) {
    const cards=checked.sleepStageCards({rem_m:100,awake_m:0,inbed_m:missing});
    assert(!cards.some(c=>c.label==='In bed'));
    assert(cards.some(c=>c.label==='Awake' && c.value==='0m'));
  }
  assert.equal(checked.sleepStageCards({inbed_m:550}).find(c=>c.label==='In bed').value,'550m');
  assert.equal(checked.sleepStageCards({inbedM:480}).find(c=>c.label==='In bed').value,'480m');
  for(const prompt of [false,true]) for(const next of ['improving','resolved']) {
    for(const outcome of ['success','lost-saved','lost-stale','lost-unavailable','lost-other-id','lost-other-state','lost-error-envelope','rejected']) {
      const f=fixture({prompt,next,outcome});
      // A previous success must not conceal a new failure.
      f.state.status={message:'Previously saved.',isError:false};
      await f.checked.commitCurrentSymptomStateChange({},f.state,f.item,next);
      const saved=outcome==='success'||outcome==='lost-saved';
      assert.equal(f.state.status.isError,!saved,`${prompt}/${next}/${outcome}`);
      assert.equal(f.counts().writes,1,'Never repeat a write on a lost receipt');
      assert.equal(f.counts().reads,outcome.startsWith('lost-')?1:0);
      assert.equal(f.state.pending,false);
      const row=f.state.member.currentSymptoms.items[0];
      if(saved && next==='resolved') assert.equal(row,undefined);
      else assert.equal(row.current_state,saved?next:'ongoing');
      if(!saved) assert.notEqual(f.state.status.message,'Previously saved.');
    }
  }
  console.log('Dashboard checks passed: missing sleep, valid zero stages, and 32 save/receipt cases.');
})().catch(error=>{console.error(error);process.exitCode=1;});
