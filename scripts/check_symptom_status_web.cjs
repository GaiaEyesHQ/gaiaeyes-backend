// Source-level browser contract checks with synthetic data and no network/DOM.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('wp-content/mu-plugins/gaia-dashboard.js', 'utf8');
const names = ['currentSymptomItemById','rebuildCurrentSymptomsSummary','updateCurrentSymptomsSnapshot',
  'upsertCurrentSymptomItem','symptomReviewDraft','commitSymptomReview'];
let code = '';
for (const name of names) {
  const start = source.indexOf('  const ' + name + ' =');
  assert(start >= 0, name);
  const end = source.indexOf('\n  const ', start + 1);
  code += source.slice(start, end) + '\n';
}
code += 'globalThis.checked = {' + names.join(',') + '};';
let posts = [], lose = true;
const context = {
  Date, crypto: require('node:crypto').webcrypto,
  maybeArray: v => Array.isArray(v) ? v : [], maybeObject: v => v && typeof v === 'object' ? v : null,
  textOrEmpty: v => v == null ? '' : String(v), cloneJson: v => JSON.parse(JSON.stringify(v)),
  extractCurrentSymptoms: v => v && (v.data || v), extractEnvelopeData: v => v.data,
  normalizeCurrentSymptomState: v => v || 'new', routeFor: () => '/synthetic/current',
  isCurrentSymptomPending: (s,id) => !!s.pending?.[id],
  setCurrentSymptomPending: (s,id,v) => { s.pending ||= {}; s.pending[id]=v; },
  setCurrentSymptomRowStatus: (s,id,message,isError) => { s.status={message,isError}; },
  renderMemberHub: () => {}, refreshSymptomGauges: () => {},
  postJson: async (url,token,body) => {
    posts.push(JSON.stringify(body));
    if (lose) { lose=false; throw new Error('synthetic lost receipt'); }
    return {ok:true,data:{id:'old-a',current_state:'resolved',activity_status:'resolved'}};
  }
};
vm.runInNewContext(code, context);
const {checked} = context;
const state={ui:{},authCtx:{token:'synthetic'},member:{errors:{},currentSymptoms:{
  items:[{id:'active',symptom_code:'HEADACHE',current_state:'ongoing',activity_status:'active'}],
  review_items:[{id:'old-a',symptom_code:'HEADACHE',label:'Headache',current_state:'ongoing',activity_status:'needs_review',updated_at:'2026-09-10T12:00:00Z',logged_at:'2026-09-01T12:00:00Z'},
    {id:'old-b',symptom_code:'HEADACHE',current_state:'ongoing',activity_status:'needs_review'}],
  recorded_items:[{id:'point',symptom_code:'HEADACHE',current_state:'new',activity_status:'recorded'}]}}};
(async () => {
  const item=checked.currentSymptomItemById(state,'old-a');
  const draft=checked.symptomReviewDraft(state,'old-a'); draft.decision='resolved';
  await checked.commitSymptomReview({},state,item);
  assert.equal(state.member.currentSymptoms.review_items.length,2);
  assert.equal(draft.request.ended_at,null);
  assert.equal(state.status.isError,true);
  await checked.commitSymptomReview({},state,item);
  assert.equal(posts.length,2);assert.equal(posts[0],posts[1]);
  assert.equal(state.member.currentSymptoms.review_items.length,1);
  assert.equal(state.member.currentSymptoms.items[0].id,'active');
  assert.equal(state.member.currentSymptoms.recorded_items[0].id,'point');
  assert.equal(state.member.currentSymptoms.summary.active_count,1);
  const newItem={id:'old-b',current_state:'ongoing',activity_status:'active'};
  checked.upsertCurrentSymptomItem(state,newItem);
  assert.equal(state.member.currentSymptoms.summary.active_count,2);
  assert.equal(state.member.currentSymptoms.review_items.length,0);
  console.log('Website synthetic retry, unknown-end and independent-bucket checks passed');
})().catch(error => { console.error(error); process.exitCode=1; });
