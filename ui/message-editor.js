(() => {
  window.dijiAttachMessageEditor = (article, {text, isBusy, onSave, note: explanation}) => {
    const button=document.createElement('button');button.type='button';button.className='message-edit-button';button.textContent='編輯';button.setAttribute('aria-label','編輯這則訊息');
    article.append(button);
    button.addEventListener('click',()=>{
      if(isBusy() || article.querySelector('.message-editor'))return;
      const form=document.createElement('form');form.className='message-editor';
      const label=document.createElement('label');label.textContent='修改已送出的訊息';
      const input=document.createElement('textarea');input.value=text;input.rows=4;input.maxLength=16000;input.required=true;label.append(input);
      const note=document.createElement('p');note.textContent=explanation || '修改後會從這一則重新生成，使用你的模型商額度。原回覆與後續內容保留在原對話。';
      const save=document.createElement('button');save.type='submit';save.className='primary-button';save.textContent='儲存並重新生成';
      const cancel=document.createElement('button');cancel.type='button';cancel.className='ghost-button';cancel.textContent='取消編輯';
      const actions=document.createElement('div');actions.className='message-editor-actions';actions.append(save,cancel);
      const status=document.createElement('p');status.setAttribute('role','status');
      let saving=false;
      cancel.addEventListener('click',()=>{if(saving)return;form.remove();button.hidden=false;button.focus();});
      form.addEventListener('submit',async event=>{
        event.preventDefault();const value=input.value.trim();if(!value || saving || isBusy())return;
        saving=true;save.disabled=true;cancel.disabled=true;input.disabled=true;save.textContent='正在重新生成…';
        try{await onSave(value);form.remove();button.hidden=false;}
        catch(error){status.textContent=error.message;}
        finally{saving=false;save.disabled=false;cancel.disabled=false;input.disabled=false;save.textContent='儲存並重新生成';}
      });
      form.append(label,note,actions,status);article.append(form);button.hidden=true;input.focus();
    });
  };
})();
