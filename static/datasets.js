// Separate dataset workspace; editor image and trace state remain untouched.
(async()=>{
 const get=id=>document.getElementById(id);
 const view=get('dataset-view');
 const fragment=await fetch('/static/dataset-panel.html');if(!fragment.ok)throw Error('No se pudo cargar el panel de datasets.');view.innerHTML=await fragment.text();
 let areas=[],lastArea=null,current=null,currentTile=null,activeJob=null,pollTimer=null,dirty=false,painting=null,tileImage=null,loadingTile=false,tileSerial=0,working=false;
 const canvas=get('ds-canvas'),context=canvas.getContext('2d'),mask=document.createElement('canvas');mask.width=mask.height=512;const maskContext=mask.getContext('2d',{willReadFrequently:true});
 let brushHover=null,maskHistory=[];
 canvas.tabIndex=0;
 function message(text,error=false){get('ds-status').textContent=text;get('ds-status').classList.toggle('error',error);}
 async function api(url,data,method='POST'){const response=await fetch(url,data===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'Error del servidor.');return result;}
 function controls(){
  const locked=!!activeJob||working;
  ['ds-source','ds-checkpoint','ds-name','ds-split','ds-choose-area','ds-bbox','ds-add-bbox','ds-gsd','ds-threshold','ds-estimate','ds-generate','ds-epochs','ds-device','ds-allow-auto','ds-datasets','ds-tiles','ds-cvat-file'].forEach(id=>get(id).disabled=locked);
  get('ds-generate').disabled=locked||!areas.length;
  get('ds-save').disabled=locked||!currentTile||loadingTile;
  get('ds-import').disabled=locked||!current||!get('ds-cvat-file').files.length;
  const missingAreas=['train','val'].filter(split=>!areas.some(area=>area.split===split));
  const names={train:'Entrenamiento',val:'Validación'};
  get('ds-split-status').textContent=missingAreas.length?`Para entrenar falta añadir una zona de ${missingAreas.map(split=>names[split]).join(' y ')}. Puedes cambiar el tipo en los desplegables de las zonas añadidas antes de descargar.`:'Zonas preparadas: hay Entrenamiento y Validación. Puedes añadir más zonas de cualquiera de los dos tipos.';
  const eligible=(current?.tiles||[]).filter(tile=>tile.reviewed||get('ds-allow-auto').checked);
  const missingTiles=['train','val'].filter(split=>!eligible.some(tile=>tile.split===split));
  get('ds-train').disabled=locked||!current||missingTiles.length>0;
  const missingSets=['train','val'].filter(split=>!current?.tiles.some(tile=>tile.split===split));
  const trainingStatus=get('ds-training-status');
  trainingStatus.classList.toggle('training-warning',!!current&&missingTiles.length>0);
  trainingStatus.textContent=!current?'Selecciona un dataset para comprobar si está listo para entrenar.':missingSets.length?`No puedes entrenar: este dataset no tiene teselas de ${missingSets.map(split=>names[split]).join(' ni ')}. Selecciona otro dataset que contenga Entrenamiento y Validación, o prepara un nuevo lote con una zona de cada tipo. Revisar máscaras o activar la casilla experimental no añade las zonas que faltan.`:missingTiles.length?`No puedes entrenar todavía: faltan máscaras revisadas de ${missingTiles.map(split=>names[split]).join(' y ')}. Selecciona teselas de esos conjuntos, revísalas y guárdalas con «He revisado esta máscara». También puedes incluir los borradores con la casilla experimental.`:`Listo para entrenar: ${eligible.filter(tile=>tile.split==='train').length} teselas de Entrenamiento y ${eligible.filter(tile=>tile.split==='val').length} de Validación disponibles.`;
  get('ds-train').title=current&&missingTiles.length?trainingStatus.textContent:'';
  const run=current?.runs.find(r=>r.id===get('ds-runs').value);get('ds-activate').disabled=locked||!run?.has_onnx;
  get('ds-cancel').disabled=!activeJob;
  ['ds-brush-tool','ds-brush-size','ds-reviewed','ds-show-mask'].forEach(id=>get(id).disabled=locked||!currentTile||loadingTile);
  ['ds-paint','ds-erase'].forEach(id=>get(id).disabled=locked||!currentTile||loadingTile);
  get('ds-undo-mask').disabled=locked||!currentTile||loadingTile||!!painting||!maskHistory.length;
  get('ds-areas').querySelectorAll('button,select').forEach(element=>element.disabled=locked);
  tileToolbar();
 }
 function tileToolbar(){
  const total=current?.tiles.length||0,reviewed=current?.tiles.filter(tile=>tile.reviewed).length||0,percent=total?reviewed/total*100:0;
  get('ds-review-progress-label').textContent=`${reviewed} / ${total} teselas revisadas · ${Math.round(percent)} %`;
  const progress=get('ds-review-progress');progress.setAttribute('aria-valuenow',String(percent));progress.setAttribute('aria-valuetext',`${reviewed} de ${total} teselas revisadas`);
  progress.style.setProperty('--review-color',`hsl(${percent*1.2} 65% 42%)`);get('ds-review-progress-fill').style.width=`${percent}%`;
  const index=current?.tiles.findIndex(tile=>tile.id===currentTile?.id)??-1,locked=!!activeJob||working||loadingTile||index<0;
  get('ds-prev-tile').disabled=locked||index<=0;get('ds-next-tile').disabled=locked||index>=current.tiles.length-1;
  get('ds-tile-position').textContent=index<0?'Sin tesela':`Tesela ${index+1} / ${current.tiles.length}`;
  const split=get('ds-tile-split'),review=get('ds-tile-review');
  split.textContent=currentTile?{train:'Entrenamiento',val:'Validación',test:'Evaluación final'}[currentTile.split]:'';split.dataset.kind=currentTile?.split||'';
  review.textContent=currentTile?(dirty?'Cambios sin guardar':currentTile.reviewed?'Revisada':'En revisión · borrador'):'';review.dataset.kind=dirty?'dirty':currentTile?.reviewed?'reviewed':'draft';
  get('ds-tile-coverage').textContent=currentTile?`${(currentTile.road_fraction*100).toFixed(1)} % vía`:'';
 }
 async function navigateTile(offset){if(!currentTile||working||activeJob||loadingTile)return;const index=current.tiles.findIndex(tile=>tile.id===currentTile.id),tile=current.tiles[index+offset];if(!tile)return;if(dirty){message('Guarda la máscara actual antes de cambiar de tesela.',true);return;}get('ds-tiles').value=tile.id;await loadTile(tile.id);}
 get('ds-prev-tile').onclick=()=>navigateTile(-1);get('ds-next-tile').onclick=()=>navigateTile(1);
 function configuration(){return {source:get('ds-source').value,name:get('ds-name').value,areas,gsd:Number(get('ds-gsd').value),threshold:Number(get('ds-threshold').value)};}
 function renderAreas(){get('ds-estimate-info').textContent='';const container=get('ds-areas');container.replaceChildren();areas.forEach((area,index)=>{
  const row=document.createElement('div');row.className='dataset-area';const label=document.createElement('small');label.textContent=`Zona ${index+1}: ${area.bbox.map(v=>v.toFixed(5)).join(', ')}`;
  const select=document.createElement('select');[['train','Entrenamiento'],['val','Validación'],['test','Evaluación final']].forEach(([value,text])=>select.add(new Option(text,value)));select.value=area.split;select.onchange=()=>{area.split=select.value;get('ds-estimate-info').textContent='';controls();};
  const remove=document.createElement('button');remove.textContent='Quitar';remove.onclick=()=>{areas.splice(index,1);renderAreas();};row.append(label,select,remove);container.append(row);
 });controls();}
 function addArea(bbox){if(areas.length>=8)throw Error('Máximo 8 zonas por lote.');if(bbox.length!==4||bbox.some(v=>!Number.isFinite(v)))throw Error('Introduce cuatro coordenadas: oeste, sur, este, norte.');areas.push({bbox,split:get('ds-split').value});renderAreas();}
 get('ds-choose-area').onclick=()=>window.areaPicker.open({initial:lastArea||{lat:Number(get('lat').value),lon:Number(get('lon').value),span:Number(get('span').value)},onApply:selection=>{
  lastArea=selection;const box=window.areaPicker.bounds(selection);
   get('ds-bbox').value=[box.getWest(),box.getSouth(),box.getEast(),box.getNorth()].map(value=>value.toFixed(7)).join(', ');
   controls();message('Bounding box preparado. Pulsa «Añadir bounding box» para incluir esta zona en el lote.');
 }});
 get('ds-add-bbox').onclick=()=>{try{addArea(get('ds-bbox').value.split(/[ ,;]+/).filter(Boolean).map(Number));message('Bounding box añadido.');}catch(e){message(e.message,true);}};
 get('ds-estimate').onclick=async()=>{try{const result=await api('/api/datasets/plan',configuration());get('ds-estimate-info').textContent=`${result.tile_count} teselas`;message('Estimación calculada. Las teselas de borde pueden extenderse hasta completar 512 píxeles.');}catch(e){message(e.message,true);}};
 ['ds-source','ds-gsd','ds-threshold'].forEach(id=>get(id).onchange=()=>{get('ds-estimate-info').textContent='';});
 let checkpointRoot='';
 function checkpointPath(){get('ds-checkpoint-path').textContent=get('ds-checkpoint').value||'Sin modelo seleccionado';}
 async function refreshCheckpoints(){const data=await api('/api/training-checkpoints'),selected=get('ds-checkpoint').value;checkpointRoot=data.root;get('ds-checkpoint').replaceChildren();for(const item of data.checkpoints)get('ds-checkpoint').add(new Option(modelOptionLabel(item.id),item.id));get('ds-checkpoint').value=data.checkpoints.some(item=>item.id===selected)?selected:data.default;checkpointPath();}
 get('ds-checkpoint').onchange=checkpointPath;
 async function refreshList(selected=current?.id){await refreshCheckpoints();const result=await api('/api/datasets');get('ds-datasets').replaceChildren(new Option('Selecciona un dataset',''));result.datasets.forEach(ds=>get('ds-datasets').add(new Option(`${ds.name} · ${ds.count} teselas · ${ds.reviewed} revisadas`,ds.id)));if(selected)get('ds-datasets').value=selected;if(!activeJob&&result.jobs.length)watch(result.jobs[0]);}
 function draw(){if(!tileImage)return;context.clearRect(0,0,512,512);context.drawImage(tileImage,0,0,512,512);if(get('ds-show-mask').checked){const coloured=document.createElement('canvas');coloured.width=coloured.height=512;const cc=coloured.getContext('2d'),pixels=maskContext.getImageData(0,0,512,512);for(let i=0;i<pixels.data.length;i+=4){const on=pixels.data[i]>127;pixels.data[i]=64;pixels.data[i+1]=235;pixels.data[i+2]=156;pixels.data[i+3]=on?110:0;}cc.putImageData(pixels,0,0);context.drawImage(coloured,0,0);}if(brushHover&&currentTile&&!working&&!activeJob){context.save();context.beginPath();context.arc(...brushHover,Number(get('ds-brush-size').value)/2,0,Math.PI*2);context.fillStyle=get('ds-brush-tool').value==='road'?'#40eb9c33':'#ed705533';context.fill();context.strokeStyle='#fff';context.lineWidth=2;context.stroke();context.strokeStyle=get('ds-brush-tool').value==='road'?'#245c3b':'#963e2b';context.lineWidth=1;context.stroke();context.restore();}}
 async function loadImage(url){const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('No se pudo cargar la tesela.'));image.src=url;});return image;}
 async function loadTile(id){
  if(dirty){get('ds-tiles').value=currentTile.id;message('Guarda la máscara actual antes de cambiar de tesela.',true);return;}
  const serial=++tileSerial;loadingTile=true;currentTile=null;controls();
  try{const tile=current.tiles.find(t=>t.id===id);if(!tile){canvas.hidden=true;get('ds-empty').hidden=false;tileImage=null;return;}
   const base=`/api/datasets/${current.id}/tiles/${id}`,stamp=Date.now();const [image,initial]=await Promise.all([loadImage(`${base}/image`),loadImage(`${base}/mask?t=${stamp}`)]);if(serial!==tileSerial)return;
   tileImage=image;currentTile=tile;maskHistory=[];brushHover=null;maskContext.drawImage(initial,0,0,512,512);get('ds-reviewed').checked=tile.reviewed;canvas.hidden=false;get('ds-empty').hidden=true;draw();
  }catch(e){message(e.message,true);}finally{if(serial===tileSerial){loadingTile=false;controls();}}
 }
 async function selectDataset(id,tileId=null){
  if(dirty){get('ds-datasets').value=current.id;message('Guarda la máscara actual antes de cambiar de dataset.',true);return;}
  current=id?await api(`/api/datasets/${id}`):null;currentTile=null;tileImage=null;canvas.hidden=true;get('ds-empty').hidden=false;
  get('ds-tiles').replaceChildren(new Option('Selecciona una tesela',''));get('ds-runs').replaceChildren(new Option('Selecciona un entrenamiento',''));
  for(const tile of current?.tiles||[])get('ds-tiles').add(new Option(`${tile.id} · ${tile.split} · ${tile.reviewed?'revisada':'borrador'} · ${(tile.road_fraction*100).toFixed(1)}% vía`,tile.id));
  for(const run of current?.runs||[])get('ds-runs').add(new Option(`${run.id} · IoU ${run.best_iou.toFixed(3)} · ${run.label_source}`,run.id));
  get('ds-directory').textContent=current?.directory||'Selecciona o prepara un dataset';get('ds-summary').textContent=current?`${current.tiles.length} teselas · ${current.tiles.filter(t=>t.reviewed).length} revisadas · modelo inicial: ${current.source_model}`:'';
  for(const [id,kind] of [['ds-export-images','images'],['ds-export-cvat','cvat'],['ds-export-bundle','bundle']]){if(current)get(id).href=`/api/datasets/${current.id}/export/${kind}`;else get(id).removeAttribute('href');}
  controls();if(current?.tiles.length){const next=current.tiles.find(tile=>tile.id===tileId)||current.tiles[0];get('ds-tiles').value=next.id;await loadTile(next.id);}
 }
 get('ds-datasets').onchange=()=>selectDataset(get('ds-datasets').value).catch(e=>message(e.message,true));get('ds-tiles').onchange=()=>loadTile(get('ds-tiles').value);get('ds-runs').onchange=controls;
 get('ds-refresh').onclick=async()=>{try{await refreshList();if(current&&!dirty)await selectDataset(current.id);}catch(e){message(e.message,true);}};
 function location(event){const rect=canvas.getBoundingClientRect();return [(event.clientX-rect.left)*512/rect.width,(event.clientY-rect.top)*512/rect.height];}
 function paint(from,to){maskContext.strokeStyle=maskContext.fillStyle=get('ds-brush-tool').value==='road'?'#fff':'#000';maskContext.lineWidth=Number(get('ds-brush-size').value);maskContext.lineCap='round';maskContext.beginPath();maskContext.moveTo(...from);maskContext.lineTo(...to);maskContext.stroke();maskContext.beginPath();maskContext.arc(...to,maskContext.lineWidth/2,0,Math.PI*2);maskContext.fill();dirty=true;get('ds-reviewed').checked=false;draw();tileToolbar();}
 function setBrush(tool){get('ds-brush-tool').value=tool;get('ds-paint').setAttribute('aria-pressed',String(tool==='road'));get('ds-erase').setAttribute('aria-pressed',String(tool==='erase'));draw();}
 get('ds-paint').onclick=()=>setBrush('road');get('ds-erase').onclick=()=>setBrush('erase');get('ds-brush-tool').onchange=()=>setBrush(get('ds-brush-tool').value);
 get('ds-brush-size').oninput=()=>{get('ds-brush-value').textContent=`${get('ds-brush-size').value} px`;draw();};
 function undoMask(){if(activeJob||working||loadingTile||painting||!currentTile||!maskHistory.length)return;const previous=maskHistory.pop();maskContext.putImageData(previous.pixels,0,0);dirty=previous.dirty;get('ds-reviewed').checked=previous.reviewed;draw();controls();message('Último trazo deshecho.');}
 get('ds-undo-mask').onclick=undoMask;
 document.addEventListener('keydown',event=>{if(view.hidden||event.target.closest('input,textarea,select,[contenteditable],dialog')||!(event.ctrlKey||event.metaKey)||event.shiftKey||event.key.toLowerCase()!=='z')return;event.preventDefault();undoMask();});
 canvas.onpointerdown=event=>{if(activeJob||working||loadingTile||!currentTile||event.button!==0)return;maskHistory.push({pixels:maskContext.getImageData(0,0,512,512),dirty,reviewed:get('ds-reviewed').checked});if(maskHistory.length>30)maskHistory.shift();painting=brushHover=location(event);canvas.setPointerCapture(event.pointerId);paint(painting,painting);controls();};
 canvas.onpointermove=event=>{brushHover=location(event);if(painting){paint(painting,brushHover);painting=brushHover;}else draw();};
 canvas.onpointerleave=()=>{brushHover=null;draw();};canvas.onpointerup=canvas.onpointercancel=()=>{painting=null;controls();};get('ds-show-mask').onchange=draw;
 get('ds-save').onclick=async()=>{if(!currentTile)return;working=true;controls();try{const pixels=maskContext.getImageData(0,0,512,512);for(let i=0;i<pixels.data.length;i+=4){const value=pixels.data[i]>127?255:0;pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=value;pixels.data[i+3]=255;}maskContext.putImageData(pixels,0,0);const tileId=currentTile.id,tileIndex=current.tiles.findIndex(tile=>tile.id===tileId),nextId=current.tiles[tileIndex+1]?.id||tileId;await api(`/api/datasets/${current.id}/tiles/${tileId}`,{mask:mask.toDataURL('image/png'),reviewed:get('ds-reviewed').checked},'PUT');dirty=false;await refreshList();await selectDataset(current.id,nextId);message('Máscara guardada.');}catch(e){message(e.message,true);}finally{working=false;controls();}};
 async function poll(){
  if(!activeJob)return;
  try{const job=await api(`/api/dataset-jobs/${activeJob.id}`);get('ds-progress').max=job.total||1;get('ds-progress').value=job.completed||0;get('ds-job-status').textContent=job.message;get('ds-log').textContent=(job.log||[]).join('\n');
   if(job.status==='running'){pollTimer=setTimeout(poll,1200);return;}
   activeJob=null;controls();await refreshList(job.dataset_id);if(!dirty)await selectDataset(job.dataset_id);message(job.message,job.status==='failed');
  }catch(e){activeJob=null;controls();message(e.message,true);}
 }
 function watch(job){activeJob=job;clearTimeout(pollTimer);controls();poll();}
 get('ds-generate').onclick=async()=>{if(dirty){message('Guarda primero la máscara que estás editando.',true);return;}try{watch(await api('/api/datasets',configuration()));}catch(e){message(e.message,true);}};
 get('ds-cancel').onclick=async()=>{try{await api(`/api/dataset-jobs/${activeJob.id}/cancel`,{});get('ds-job-status').textContent='Cancelando…';}catch(e){message(e.message,true);}};
 get('ds-cvat-file').onchange=controls;
 get('ds-allow-auto').onchange=controls;
 get('ds-import').onclick=async()=>{if(dirty){message('Guarda primero la máscara actual.',true);return;}working=true;controls();try{const body=new FormData();body.append('file',get('ds-cvat-file').files[0]);const response=await fetch(`/api/datasets/${current.id}/import-cvat`,{method:'POST',body});const result=await response.json();if(!response.ok)throw Error(result.error);get('ds-cvat-file').value='';await refreshList();await selectDataset(current.id);message(`${result.imported} máscaras revisadas importadas.`);}catch(e){message(e.message,true);}finally{working=false;controls();}};
 get('ds-train').onclick=async()=>{if(dirty){message('Guarda primero la máscara actual.',true);return;}if(!get('ds-epochs').reportValidity())return;try{watch(await api(`/api/datasets/${current.id}/train`,{epochs:Number(get('ds-epochs').value),device:get('ds-device').value,checkpoint:get('ds-checkpoint').value,allow_automatic:get('ds-allow-auto').checked}));}catch(e){message(e.message,true);}};
 get('ds-activate').onclick=async()=>{try{const result=await api(`/api/datasets/${current.id}/runs/${get('ds-runs').value}/activate`,{});resetResults();showModel(result.model);await refreshEditorModels();message('Modelo activado. Ya puedes utilizarlo en el editor y en Wololo.');}catch(e){message(e.message,true);}};
 function switchPage(dataset){if(busy){message('Espera a que termine la operación del editor.',true);return;}get('editor-view').hidden=dataset;view.hidden=!dataset;get('nav-editor').setAttribute('aria-pressed',String(!dataset));get('nav-datasets').setAttribute('aria-pressed',String(dataset));if(!dataset)resizeViewer();else refreshList().catch(e=>message(e.message,true));}
 get('nav-editor').onclick=()=>switchPage(false);get('nav-datasets').onclick=()=>switchPage(true);get('nav-datasets').disabled=false;controls();
})().catch(error=>{document.getElementById('nav-datasets').disabled=true;console.error(error);});
