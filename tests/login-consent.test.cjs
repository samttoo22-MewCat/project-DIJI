const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test/',runScripts:'outside-only'}),w=dom.window;
w.matchMedia=()=>({matches:false,addEventListener(){}});w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
let fail=false,oauthFetches=0;
w.fetch=async(url)=>{
 if(url==='/api/legal')return {ok:!fail,json:async()=>({version:'a'.repeat(64),updated:'2026-11-01'})};
 if(url==='/api/auth/session')return {ok:true,json:async()=>({authenticated:false,auth_required:true,user:null})};
 if(url.includes('/api/auth/google/start'))oauthFetches++;
 return {ok:true,json:async()=>[]};
};
w.eval(fs.readFileSync(path.join(root,'ui/app.js'),'utf8'));
const d=w.document,tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{
 await tick();assert.equal(d.querySelector('#google-login-dialog').open,false);
 d.querySelector('#account-login').click();await tick();
 const agreement=d.querySelector('#login-terms-agreed'),button=d.querySelector('#google-login'),form=d.querySelector('#google-login-form');
 assert.equal(agreement.checked,false);assert.equal(button.disabled,true);assert.equal(form.method,'post');assert.equal(new URL(form.action).pathname,'/api/auth/google/start');
 assert.equal(d.querySelector('.login-legal-links a').getAttribute('target'),'_blank');assert.match(d.querySelector('.login-data-note').textContent,/對話、記憶與生成流程紀錄/);
 let event=new w.Event('submit',{cancelable:true});form.dispatchEvent(event);assert.equal(event.defaultPrevented,true);
 agreement.checked=true;agreement.dispatchEvent(new w.Event('change'));assert.equal(button.disabled,false);
 event=new w.Event('submit',{cancelable:true});form.dispatchEvent(event);assert.equal(event.defaultPrevented,false);assert.equal(oauthFetches,0);
 assert.equal(d.querySelector('#login-policy-version').value,'a'.repeat(64));
 d.querySelector('[data-google-login-close]').click();d.querySelector('#account-login').click();await tick();assert.equal(agreement.checked,false);assert.equal(button.disabled,true);
 d.querySelector('[data-google-login-close]').click();fail=true;d.querySelector('#account-login').click();await tick();agreement.checked=true;agreement.dispatchEvent(new w.Event('change'));
 assert.equal(button.disabled,true);assert.match(d.querySelector('#google-login-status').textContent,/無法讀取條款/);
 console.log('PASS: prior disclosure, unchecked consent, current version, native POST, reset and fail-closed metadata');w.close();
})().catch(e=>{console.error(e);w.close();process.exitCode=1});
