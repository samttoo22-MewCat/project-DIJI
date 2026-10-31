(() => {
  const dialog = document.createElement('dialog'); dialog.className='memory-editor-dialog'; dialog.setAttribute('aria-labelledby','memory-editor-title');
  dialog.innerHTML = `<form id="memory-edit-form"><header><p class="eyebrow">謹慎操作</p><h2 id="memory-editor-title"></h2></header><p class="memory-edit-warning" id="memory-edit-warning"></p><blockquote id="memory-delete-preview" hidden></blockquote><div id="memory-edit-fields"><label>記憶分類<select name="type"><option>事實</option><option>偏好</option><option>事件</option><option>標記</option><option value="event">事件（舊格式）</option></select></label><label>記憶摘要（最多 60 字）<textarea name="summary" maxlength="60" rows="3" required></textarea></label><label>關鍵字（每行「分類：內容」）<textarea name="keywords" rows="4" placeholder="人物：青禾、夜蘭&#10;地點：月橋書店"></textarea></label><label>關鍵重點（每行一項，最多 5 項）<textarea name="key_points" rows="3"></textarea></label><label>角色回覆摘要<textarea name="character_response_summary" maxlength="2000" rows="3"></textarea></label><p class="memory-edit-note">原始使用者訊息與記憶時間不會被修改。</p></div><label class="memory-delete-ack" id="memory-delete-ack" hidden><input type="checkbox" id="memory-delete-confirmed" />我了解刪除後無法直接復原</label><p id="memory-edit-status" role="status" aria-live="polite"></p><div class="memory-editor-actions"><button class="ghost-button" id="memory-edit-cancel" type="button">取消</button><button class="primary-button" id="memory-edit-save" type="submit">儲存變更</button></div></form>`;
  document.body.append(dialog);
  const form=dialog.querySelector('form'), find=id=>dialog.querySelector('#'+id), field=name=>form.elements.namedItem(name);
  let target=null, busy=false;
  function setBusy(value){busy=value;form.setAttribute('aria-busy',String(value));form.querySelectorAll('button,input,textarea,select').forEach(element=>element.disabled=value);if(!value && target?.mode==='delete')find('memory-edit-save').disabled=!find('memory-delete-confirmed').checked;}
  function open(mode,memory,chatId,done){
    if(dialog.open || busy)return;
    target={mode,memory,chatId,done};
    find('memory-editor-title').textContent=mode==='edit'?'編輯這筆記憶':'確定刪除這筆記憶？';
    find('memory-edit-warning').textContent=mode==='edit'?'記憶會影響角色後續的回憶與回覆。請只修改已確認的內容，保存後會直接取代這筆記憶。':'刪除會讓角色之後無法從這筆記憶讀取內容，且無法直接復原。原始對話不會刪除，也仍可能出現在對話歷史中。';
    find('memory-edit-fields').hidden=mode==='delete';find('memory-delete-preview').hidden=mode!=='delete';find('memory-delete-ack').hidden=mode!=='delete';
    find('memory-delete-preview').textContent=memory.summary;find('memory-delete-confirmed').checked=false;
    field('type').value=memory.type;field('summary').value=memory.summary;
    field('keywords').value=Object.entries(memory.keywords||{}).map(([key,value])=>`${key}：${value}`).join('\n');
    field('key_points').value=(memory.key_points||[]).join('\n');field('character_response_summary').value=memory.character_response_summary||'';
    find('memory-edit-fields').querySelectorAll('input,textarea,select').forEach(element=>element.required=mode==='edit' && element.name==='summary');
    find('memory-edit-status').textContent='';find('memory-edit-save').className=mode==='delete'?'danger-button':'primary-button';find('memory-edit-save').textContent=mode==='delete'?'確認刪除':'儲存變更';
    setBusy(false);dialog.showModal();(mode==='edit'?field('summary'):find('memory-edit-cancel')).focus();
  }
  find('memory-edit-cancel').addEventListener('click',()=>{if(!busy)dialog.close();});
  dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  find('memory-delete-confirmed').addEventListener('change',()=>find('memory-edit-save').disabled=!find('memory-delete-confirmed').checked);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy || !target)return;
    const snapshot=target;let changes;
    try {
      if(snapshot.mode==='delete' && !find('memory-delete-confirmed').checked)return;
      if(snapshot.mode==='edit'){
        const keywords={};for(const line of field('keywords').value.split('\n').filter(line=>line.trim())){const match=line.match(/^([^:：]+)[:：](.+)$/);if(!match || !match[1].trim() || !match[2].trim())throw Error('關鍵字請使用「分類：內容」，每行一組。');const key=match[1].trim();if(Object.hasOwn(keywords,key))throw Error('同一分類請放在同一行，可用頓號分隔多個值。');Object.defineProperty(keywords,key,{value:match[2].trim(),enumerable:true});}
        const points=field('key_points').value.split('\n').map(value=>value.trim()).filter(Boolean);
        if(points.length>5)throw Error('關鍵重點最多 5 項。');if(Object.keys(keywords).length>32)throw Error('關鍵字分類最多 32 組。');
        const summary=field('summary').value.trim();if(!summary)throw Error('請填寫記憶摘要。');
        changes={type:field('type').value,summary,keywords,key_points:points,character_response_summary:field('character_response_summary').value.trim()||null};
      }
      setBusy(true);find('memory-edit-status').textContent=snapshot.mode==='edit'?'正在儲存…':'正在刪除…';
      const response=await fetch(`/api/memories/${encodeURIComponent(snapshot.chatId)}/entries/${encodeURIComponent(snapshot.memory.record_id)}`,{method:snapshot.mode==='edit'?'PATCH':'DELETE',headers:snapshot.mode==='edit'?{'Content-Type':'application/json'}:undefined,body:changes?JSON.stringify(changes):undefined});
      if(!response.ok)throw Error(response.status===404?'記憶已被變更或不存在。請取消並重新開啟記憶頁後再試。':'操作未完成，請確認登入或稍後重試。');
      dialog.close();await snapshot.done();
    }catch(error){find('memory-edit-status').textContent=error.message;}
    finally{setBusy(false);}
  });
  window.dijiMemoryEditor={open};
})();
