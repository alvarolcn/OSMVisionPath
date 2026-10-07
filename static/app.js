let requestedBBox=null,requestedPolygon=null,loadedPolygon=null;
function projectedSelection(selection){const box=window.areaPicker.bounds(selection);return [box.getWest(),box.getSouth(),box.getEast(),box.getNorth()].map((v,i)=>i%2?6378137*Math.log(Math.tan(Math.PI/4+v*Math.PI/360)):6378137*v*Math.PI/180);}
const savedEditorArea=window.areaPicker.saved('editor');if(savedEditorArea?.selection?.height){requestedBBox=projectedSelection(savedEditorArea.selection);requestedPolygon=normalizedPolygon(savedEditorArea.selection,requestedBBox);}
function normalizedPolygon(selection,box){if(!selection.polygon)return null;return selection.polygon.map(([lon,lat])=>[(6378137*lon*Math.PI/180-box[0])/(box[2]-box[0]),(box[3]-6378137*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360)))/(box[3]-box[1])]).map(p=>p.map(v=>Math.max(0,Math.min(1,v))));}
function planeHeight(){return image?1024*image.naturalHeight/image.naturalWidth:1024;}
let loadedSource="pnoa";
const $ = id => document.getElementById(id);
const canvas = $('map'), ctx = canvas.getContext('2d');
canvas.tabIndex=0;
let image=null,bbox=null,points=[],paths=[],selected=-1,geojson=null,busy=false,frame=null,visible=Infinity,modelReady=false;
let zoom=1,panX=0,panY=0,drag=null;
let viewWidth=1024,viewHeight=1024,fitScale=1,pixelRatio=1;
function viewScale(){return fitScale*zoom;}
function resizeViewer(reset=false){
  const width=$('viewport').clientWidth,height=$('viewport').clientHeight;
  if(!width||!height)return;
  const center=[(viewWidth/2-panX)/viewScale()/1024,(viewHeight/2-panY)/viewScale()/planeHeight()];
  viewWidth=width;viewHeight=height;fitScale=Math.min(width/1024,height/planeHeight());pixelRatio=window.devicePixelRatio||1;
  canvas.width=Math.round(width*pixelRatio);canvas.height=Math.round(height*pixelRatio);
  panX=width/2-(reset ? .5 : center[0])*1024*viewScale();panY=height/2-(reset ? .5 : center[1])*planeHeight()*viewScale();
  hoverPoint=null;clampPan();draw();
}
new ResizeObserver(()=>resizeViewer()).observe($('viewport'));
let detectedMask=null;
let areaDirty=false;
let traceHistory=[];
let wololoState=null,wololoCorrection=false;
let pointIds=[],selectedPointId=null;
let hoverPoint=null;
let traceEdit=null;
function setPoints(value){points=value;pointIds=value.map((_,i)=>i+1);selectedPointId=null;}
function nextPointId(){const used=new Set(pointIds);let id=1;while(used.has(id))id++;return id;}
function addPoint(at,index=points.length){const id=nextPointId();if($('mode').value==='wololo'){const next=pointIds.findIndex(value=>value>id);index=next<0?points.length:next;}points.splice(index,0,at);pointIds.splice(index,0,id);selectedPointId=id;}
function saveTrace(){traceHistory.push(structuredClone({paths,geojson,points,pointIds,selectedPointId,selected}));if(traceHistory.length>40)traceHistory.shift();}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function loading(show,text='Cargando la ortofoto de la fuente seleccionada…'){$('ortho-loader').hidden=!show;$('loader-message').textContent=text;$('viewport').setAttribute('aria-busy',String(show));}
function controls(){
  $('review-export-controls').disabled=busy||areaDirty||!!wololoState||!geojson||!paths.length;
  $('tool-hand').disabled=busy;$('tool-nodes').disabled=busy||areaDirty;
  const guided=$('mode').value==='wololo',review=!!wololoState;
  ['delete-trace','split-trace'].forEach(id=>$(id).disabled=busy||areaDirty||review||selected<0||!!traceEdit);
  $('join-traces').disabled=busy||areaDirty||review||selected<0||paths.length<2;
  $('split-trace').setAttribute('aria-pressed',String(traceEdit?.mode==='split'));
  $('join-traces').setAttribute('aria-pressed',String(traceEdit?.mode==='join'));
  const segmentation=$('mode').value==='segmentation';
  if(segmentation)$('tool').value='select';
  $('tool').closest('label').hidden=segmentation;
  $('count').parentElement.hidden=segmentation;
  $('tool-nodes').hidden=segmentation;
  $('edit-candidate').hidden=segmentation;
  toolHelp();
  $('load').disabled=busy;
  $('auto-detect').disabled=busy||!image||areaDirty||($('mode').value==='segmentation'&&!modelReady);
  $('detect').disabled=busy||!image||areaDirty||points.length<2;
  $('undo').disabled=busy||!points.length;$('clear').disabled=busy||!points.length;
  $('export').disabled=busy||!geojson||!paths.length;$('replay').disabled=busy||!paths.length;
  $('export-osm').disabled=busy||!geojson||!paths.length;
  $('undo-trace').disabled=busy||!traceHistory.length;
  $('simplify').disabled=busy||!paths.length||($('simplify-scope').value==='selected'&&selected<0);
  $('remove-candidate').disabled=$('edit-candidate').disabled=busy||selected<0;
  ['ortho-max-mp','ortho-use-recommended','ortho-gsd','ortho-source','editor-model','refresh-editor-models','lat','lon','span','sensitivity','mode','threshold','candidate','tool','model-file','choose-area','simplify-scope','simplify-tolerance','wololo-limit','wololo-tolerance'].forEach(id=>$(id).disabled=busy);
  $('upload-model').disabled=busy||!$('model-file').files.length;
  $('count').textContent=`${points.length} puntos`;
  $('auto-detect').hidden=$('detect').hidden=guided;
  $('full-area-controls').hidden=guided;
  $('wololo-panel').hidden=!guided;
  $('color-correction').hidden=guided||segmentation;
  $('wololo-start').disabled=busy||!image||areaDirty||!modelReady||points.length<2||review;
  ['wololo-confirm','wololo-correct','wololo-finish','wololo-reset'].forEach(id=>$(id).disabled=busy);
  $('wololo-back').disabled=busy||!wololoState||!wololoState.accepted.length;
  if(guided||segmentation){$('detect').disabled=true;$('edit-candidate').disabled=true;}
  if(traceEdit){['simplify','remove-candidate','edit-candidate','auto-detect','wololo-start'].forEach(id=>$(id).disabled=true);}
  if(review){['simplify','undo-trace','remove-candidate','candidate','undo','clear'].forEach(id=>$(id).disabled=true);}
}
function screenPoint(event){const rect=canvas.getBoundingClientRect();return [(event.clientX-rect.left)*viewWidth/rect.width,(event.clientY-rect.top)*viewHeight/rect.height];}
function imagePoint(event){const [x,y]=screenPoint(event);return [(x-panX)/viewScale()/1024,(y-panY)/viewScale()/planeHeight()];}
function draw(){
  if(!image)return;
  ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#dfe5dc';ctx.fillRect(0,0,canvas.width,canvas.height);
  const scale=viewScale();ctx.setTransform(scale*pixelRatio,0,0,scale*pixelRatio,panX*pixelRatio,panY*pixelRatio);ctx.drawImage(image,0,0,1024,planeHeight());
  if(detectedMask&&$('show-mask').checked){ctx.globalAlpha=.4;ctx.drawImage(detectedMask,0,0,1024,planeHeight());ctx.globalAlpha=1;}
  if($('overlay').checked)paths.forEach((line,index)=>{
    ctx.beginPath();line.slice(0,visible).forEach(([x,y],i)=>{if(i)ctx.lineTo(x*1024,y*planeHeight());else ctx.moveTo(x*1024,y*planeHeight());});
    ctx.lineJoin='round';ctx.strokeStyle='rgba(18,49,28,.8)';ctx.lineWidth=7/viewScale();ctx.stroke();
    ctx.strokeStyle=index===selected?'#ffbe52':'#b9f55c';ctx.lineWidth=3/viewScale();ctx.stroke();
  });
  points.forEach(([x,y],i)=>{ctx.beginPath();ctx.arc(x*1024,y*planeHeight(),10/viewScale(),0,Math.PI*2);ctx.fillStyle=pointIds[i]===selectedPointId?'#ffbe52':'#fff';ctx.fill();ctx.strokeStyle='#315638';ctx.lineWidth=2/viewScale();ctx.stroke();ctx.fillStyle='#274d39';ctx.font=`bold ${12/viewScale()}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(pointIds[i],x*1024,y*planeHeight());});
  if(hoverPoint&&!busy&&!drag&&$('tool').value==='correct'&&(!wololoState||wololoCorrection)&&!points.some(p=>Math.hypot(p[0]-hoverPoint[0],(p[1]-hoverPoint[1])*planeHeight()/1024)*1024*viewScale()<16)){
    const [x,y]=hoverPoint;ctx.beginPath();ctx.arc(x*1024,y*planeHeight(),10/viewScale(),0,Math.PI*2);ctx.fillStyle='#ffffffaa';ctx.fill();ctx.strokeStyle='#315638';ctx.lineWidth=2/viewScale();ctx.setLineDash([3/viewScale(),3/viewScale()]);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#274d39';ctx.font=`bold ${12/viewScale()}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(nextPointId(),x*1024,y*planeHeight());
  }
  if(wololoState){const pending=wololoState.sections[wololoState.index];if(pending){ctx.beginPath();pending.path.forEach(([x,y],i)=>i?ctx.lineTo(x*1024,y*planeHeight()):ctx.moveTo(x*1024,y*planeHeight()));ctx.strokeStyle='#ff8b26';ctx.lineWidth=4/viewScale();ctx.setLineDash([8/viewScale(),5/viewScale()]);ctx.stroke();ctx.setLineDash([]);}}
  if(loadedPolygon){ctx.save();ctx.beginPath();ctx.rect(0,0,1024,planeHeight());loadedPolygon.forEach(([x,y],i)=>i?ctx.lineTo(x*1024,y*planeHeight()):ctx.moveTo(x*1024,y*planeHeight()));ctx.closePath();ctx.fillStyle='#13251c88';ctx.fill('evenodd');ctx.beginPath();loadedPolygon.forEach(([x,y],i)=>i?ctx.lineTo(x*1024,y*planeHeight()):ctx.moveTo(x*1024,y*planeHeight()));ctx.closePath();ctx.strokeStyle='#f4c357';ctx.lineWidth=2/viewScale();ctx.stroke();ctx.restore();}
  if(traceEdit?.bridge){ctx.beginPath();traceEdit.bridge.forEach(([x,y],i)=>i?ctx.lineTo(x*1024,y*planeHeight()):ctx.moveTo(x*1024,y*planeHeight()));ctx.strokeStyle='#ff8b26';ctx.lineWidth=4/viewScale();ctx.setLineDash([7/viewScale(),5/viewScale()]);ctx.stroke();ctx.setLineDash([]);}
  ctx.setTransform(1,0,0,1,0,0);
}
function updateCandidates(){
  const select=$('candidate');select.replaceChildren();
  if(!paths.length){const option=new Option('Sin trazados','');select.add(option);selected=-1;}
  paths.forEach((line,i)=>select.add(new Option(`Trazado ${i+1} · ${line.length} vértices`,i)));
  select.value=String(selected);$('length').textContent=`${paths.length} trazados`;controls();draw();
}
function resetResults(){traceEdit=null;wololoState=null;wololoCorrection=false;$('wololo-review').hidden=true;$('wololo-info').textContent='';cancelAnimationFrame(frame);paths=[];selected=-1;geojson=null;visible=Infinity;detectedMask=null;traceHistory=[];$('simplify-info').textContent='';$('detection-info').textContent='';updateCandidates();}
function showModel(name){modelReady=!!name;$('model-status').textContent=name?`Modelo activo: ${name}`:'No hay modelo activo';$('model-hint').textContent=name?'Ya puedes detectar. Cargar otro archivo es opcional.':'Carga un ONNX para usar la segmentación.';$('replace-model').open=!modelReady;controls();}
async function refreshModel(){const response=await fetch('/api/health');if(!response.ok)throw Error('No se pudo consultar el modelo del servidor.');const data=await response.json();$('version').textContent=`OpenCV ${data.opencv} · local`;showModel(data.model);await refreshEditorModels();}
function modelOptionLabel(path){if(['models/best.th','models/model.onnx'].includes(path))return 'Modelo predeterminado';const parts=path.split('/'),run=parts.find(part=>part.startsWith('run-'));return run?`Entrenado · ${run}`:parts[parts.length-1];}
async function refreshEditorModels(){const response=await fetch('/api/editor-models');if(!response.ok)throw Error('No se pudo consultar la lista de ONNX. Reinicia Flask si acabas de actualizar el proyecto.');const data=await response.json();const match=data.models.find(item=>item.id===data.active||item.id.split('/').pop()===data.active||item.id==='datasets/'+data.active+'/model.onnx');$('editor-model').replaceChildren();if(!match)$('editor-model').add(new Option(data.active?'Modelo cargado externamente':'Selecciona un modelo',''));for(const item of data.models)$('editor-model').add(new Option(item.title?`${item.title} · ${new Date(item.exported_at*1000).toLocaleDateString('es-ES')}${item.run?' · '+item.run:''}`:modelOptionLabel(item.id),item.id));if(match)$('editor-model').value=match.id;$('editor-model-path').textContent=match?match.id:(data.active||'Sin modelo seleccionado');}
$('refresh-editor-models').onclick=()=>refreshEditorModels().catch(error=>status(error.message,true));
$('editor-model').onchange=async()=>{const chosen=$('editor-model').value;if(!chosen)return;busy=true;controls();try{const result=await api('/api/editor-models/activate',{model:chosen});resetResults();showModel(result.model);await refreshEditorModels();status('Modelo seleccionado y activado.');}catch(error){status(error.message,true);await refreshEditorModels();}finally{busy=false;controls();}};
$('model-file').onchange=controls;
$('ortho-gsd').onchange=()=>{if(image){areaDirty=true;status('Resolucion cambiada. Vuelve a cargar la misma area.');}controls();};
$('ortho-source').onchange=()=>{if(image){areaDirty=true;status('Fuente cambiada. Vuelve a cargar la misma area.');}controls();};
$('choose-area').onclick=()=>{if(!busy)window.areaPicker.open();};
function changedArea(){requestedBBox=null;requestedPolygon=null;if(image){areaDirty=true;setPoints([]);resetResults();$('resolution').textContent='Área nueva pendiente de cargar';status('El área seleccionada ha cambiado. Pulsa Cargar ortofoto para analizar esa zona.');}$('area-summary').textContent=`Centro ${Number($('lat').value).toFixed(6)}, ${Number($('lon').value).toFixed(6)} · ${$('span').value} m`;controls();}
window.addEventListener('area-picked',event=>{changedArea();requestedBBox=projectedSelection(event.detail);requestedPolygon=normalizedPolygon(event.detail,requestedBBox);$('area').requestSubmit();});
['lat','lon','span'].forEach(id=>$(id).addEventListener('change',changedArea));
async function maskOverlay(source){const loaded=new Image();await new Promise((resolve,reject)=>{loaded.onload=resolve;loaded.onerror=()=>reject(Error('No se pudo mostrar la máscara detectada.'));loaded.src=source;});const overlay=document.createElement('canvas');overlay.width=loaded.width;overlay.height=loaded.height;const context=overlay.getContext('2d');context.drawImage(loaded,0,0);const pixels=context.getImageData(0,0,overlay.width,overlay.height);for(let i=0;i<pixels.data.length;i+=4){const on=pixels.data[i]>0;pixels.data[i]=70;pixels.data[i+1]=235;pixels.data[i+2]=160;pixels.data[i+3]=on?255:0;}context.putImageData(pixels,0,0);return overlay;}
async function api(endpoint,data){const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'Error de conexión.');return result;}
function animate(){cancelAnimationFrame(frame);const start=performance.now(),max=Math.max(...paths.map(p=>p.length),0);function tick(now){visible=Math.max(2,Math.ceil((now-start)/2200*max));draw();if(visible<max)frame=requestAnimationFrame(tick);else visible=Infinity;}frame=requestAnimationFrame(tick);}
function setZoom(next,center=[viewWidth/2,viewHeight/2]){next=Math.max(1,Math.min(8,next));const ratio=next/zoom;panX=center[0]-(center[0]-panX)*ratio;panY=center[1]-(center[1]-panY)*ratio;zoom=next;clampPan();hoverPoint=null;$('zoom-value').textContent=`${Math.round(zoom*100)}%`;draw();}
function clampPan(){const size=1024*viewScale();let constHeight;panX=size<=viewWidth?(viewWidth-size)/2:Math.max(viewWidth-size,Math.min(0,panX));constHeight=planeHeight()*viewScale();panY=constHeight<=viewHeight?(viewHeight-constHeight)/2:Math.max(viewHeight-constHeight,Math.min(0,panY));}
$('zoom-in').onclick=()=>setZoom(zoom*1.4);$('zoom-out').onclick=()=>setZoom(zoom/1.4);$('zoom-reset').onclick=()=>setZoom(1);
$('zoom-fill').onclick=()=>setZoom(Math.max(viewWidth/1024,viewHeight/planeHeight())/fitScale);
canvas.addEventListener('wheel',event=>{if(!image)return;event.preventDefault();setZoom(zoom*Math.exp(-event.deltaY*.0015),screenPoint(event));},{passive:false});
function toolHelp(){const correct=$('tool').value==='correct';$('tool-hand').setAttribute('aria-pressed',String(!correct));$('tool-nodes').setAttribute('aria-pressed',String(correct));$('edit-help').textContent=$('mode').value==='segmentation'?'Arrastra con la mano para mover la imagen. Usa la rueda para ampliar y pulsa un trazado para seleccionarlo.':correct?'Pulsa para añadir un marcador o seleccionarlo. Suprimir elimina el seleccionado. Arrastra el fondo para mover la vista o un marcador para moverlo; Shift + arrastrar siempre mueve la vista. S o Esc vuelve a la mano.':'Arrastra con la mano para mover la imagen. A activa los marcadores; pulsa uno y Suprimir para eliminarlo. Usa la rueda para ampliar.';canvas.classList.toggle('split-cursor',traceEdit?.mode==='split');canvas.style.cursor=traceEdit?.mode==='split'?'':correct?'crosshair':'grab';}
$('tool').onchange=()=>{wololoCorrection=$('tool').value==='correct'&&!!wololoState;toolHelp();draw();};
$('tool-hand').onclick=()=>{$('tool').value='select';$('tool').onchange();canvas.focus({preventScroll:true});};
$('tool-nodes').onclick=()=>{$('tool').value='correct';$('tool').onchange();canvas.focus({preventScroll:true});};
document.addEventListener('keydown',event=>{
  if($('editor-view').hidden||busy||!image||event.ctrlKey||event.metaKey||event.altKey||event.target.closest('input,select,textarea,[contenteditable="true"]')||document.querySelector('dialog[open]'))return;
  if(event.key.toLowerCase()==='c'){event.preventDefault();joinTrace();return;}
  if(event.key.toLowerCase()==='a'){if(areaDirty||$('mode').value==='segmentation')return;event.preventDefault();$('tool').value='correct';if(wololoState)wololoCorrection=true;toolHelp();draw();status('Marcador activo. Pulsa sobre la imagen para añadir un punto. S o Esc vuelve a la mano.');}
  else if(event.key==='Escape'||event.key.toLowerCase()==='s'){traceEdit=null;controls();event.preventDefault();$('tool').value='select';wololoCorrection=false;toolHelp();draw();}
  else if(event.key==='Delete'){
    if(areaDirty)return;
    const index=$('tool').value==='correct'?pointIds.indexOf(selectedPointId):-1;
    if(index<0){if(selected>=0&&!wololoState){event.preventDefault();$('remove-candidate').click();}return;}
    event.preventDefault();saveTrace();const id=pointIds[index];points.splice(index,1);pointIds.splice(index,1);selectedPointId=null;
    if(wololoState){wololoState=null;wololoCorrection=false;$('wololo-review').hidden=true;}
    controls();draw();status(`Marcador ${id} eliminado. Su número queda disponible; los demás conservan su número. Recalcula para aplicar el cambio.`);
  }
});
canvas.addEventListener('pointerdown',event=>{
  if(busy||!image||event.button!==0)return;
  canvas.focus({preventScroll:true});
  const at=imagePoint(event);let point=-1;
  if(!event.shiftKey)point=points.findIndex(p=>Math.hypot(p[0]-at[0],(p[1]-at[1])*planeHeight()/1024)*1024*viewScale()<16);
  if(point>=0)selectedPointId=pointIds[point];
  drag={start:screenPoint(event),last:screenPoint(event),point,moved:false,pan:$('tool').value==='select'||event.shiftKey||!!wololoState&&point>=0};
  if(drag.pan)canvas.style.cursor='grabbing';
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove',event=>{
  if(!drag){hoverPoint=imagePoint(event);draw();return;}const at=screenPoint(event);if(Math.hypot(at[0]-drag.start[0],at[1]-drag.start[1])>5)drag.moved=true;
  if(drag.moved&&!drag.pan&&drag.point<0){drag.pan=true;drag.last=drag.start;canvas.style.cursor='grabbing';}
  if(drag.pan){panX+=at[0]-drag.last[0];panY+=at[1]-drag.last[1];clampPan();}
  else if(drag.point>=0&&drag.moved){if(!drag.saved){saveTrace();drag.saved=true;}points[drag.point]=imagePoint(event).map(v=>Math.max(0,Math.min(1,v)));controls();}
  drag.last=at;draw();
});
function nearest(at){const aspect=planeHeight()/1024;let best=-1,distance=14/(1024*viewScale());paths.forEach((line,i)=>{for(let j=1;j<line.length;j++){const a=line[j-1],b=line[j],dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((at[0]-a[0])*dx+(at[1]-a[1])*dy*aspect*aspect)/(dx*dx+dy*dy*aspect*aspect||1)));const d=Math.hypot(at[0]-a[0]-t*dx,(at[1]-a[1]-t*dy)*aspect);if(d<distance){distance=d;best=i;}}});return best;}
canvas.addEventListener('pointerup',event=>{
  if(!drag)return;const current=drag;drag=null;canvas.releasePointerCapture(event.pointerId);toolHelp();
  if(current.moved)return;const at=imagePoint(event);if(at.some(v=>v<0||v>1))return;
  if(traceEdit){traceEditClick(at);return;}
  if(current.point>=0&&!event.shiftKey){selectedPointId=pointIds[current.point];draw();status(`Marcador ${selectedPointId} seleccionado. Suprimir lo elimina.`);return;}
  if($('tool').value==='select'){selected=nearest(at);updateCandidates();return;}
  if(current.point>=0||event.shiftKey)return;
  if($('mode').value==='wololo'){
    if(wololoState){if(wololoCorrection){wololoCorrection=false;runWololo(at);}else status('Confirma el tramo naranja o pulsa Corregir dirección.');return;}
    if(points.length>=2){if(points.length<20){saveTrace();addPoint(at);controls();draw();status(`Marcador ${selectedPointId} añadido. Wololo recorrerá los marcadores en orden y terminará en el último.`);}return;}
    saveTrace();addPoint(at);controls();draw();status(points.length===1?'Inicio marcado. Marca el punto final.':'Inicio y fin preparados. Pulsa Trazar con Wololo.');return;
  }
  if(points.length>=20){status('Máximo 20 puntos. Deshaz uno para corregirlo.',true);return;}
  saveTrace();addPoint(at);controls();draw();status('Puntos modificados. Pulsa Recalcular con puntos para aplicar la corrección.');
});
canvas.addEventListener('pointercancel',()=>{drag=null;toolHelp();});
canvas.addEventListener('pointerleave',()=>{hoverPoint=null;draw();});
$('area').addEventListener('submit',async event=>{
  let progressTimer=null;const progressId=crypto.randomUUID().replaceAll('-','');
  event.preventDefault();if(busy)return;if(!$('ortho-max-mp').reportValidity())return;busy=true;controls();loading(true,'Descargando la ortofoto de la fuente seleccionada a la resolución elegida…');status('Descargando la ortofoto de la fuente seleccionada…');
  try{progressTimer=setInterval(async()=>{try{const response=await fetch(`/api/ortho-progress/${progressId}`);if(!response.ok)return;const progress=await response.json();if(progressTimer!==null&&progress.total)loading(true,`Descargando teselas: ${progress.completed} / ${progress.total}`);}catch{}},1000);const result=await api('/api/ortho',{max_megapixels:Number($('ortho-max-mp').value),polygon:requestedPolygon,gsd:Number($('ortho-gsd').value),progress_id:progressId,...(requestedBBox?{bbox:requestedBBox}:{}),source:$('ortho-source').value,lat:Number($('lat').value),lon:Number($('lon').value),span:Number($('span').value)});loading(true,'Preparando la ortofoto y el zoom…');const loaded=new Image();await new Promise((resolve,reject)=>{loaded.onload=resolve;loaded.onerror=()=>reject(Error('No se pudo mostrar la imagen.'));loaded.src=result.image;});await loaded.decode();image=loaded;loadedPolygon=requestedPolygon?structuredClone(requestedPolygon):null;bbox=result.bbox;loadedSource=result.source||'pnoa';$('ortho-provider').textContent=loadedSource==='itacyl'?'ITACyL Castilla y Le\u00f3n':'PNOA IGN';$('ortho-attribution').textContent=loadedSource==='itacyl'?'ITACyL / Junta de Castilla y Le\u00f3n':'IGN / PNOA';areaDirty=false;setPoints([]);canvas.hidden=false;$('empty').hidden=true;resetResults();zoom=1;resizeViewer(true);setZoom(1);const spacing=result.meters_per_pixel??Number($('span').value)/loaded.naturalWidth;$('resolution').textContent=`${result.width||loaded.naturalWidth} × ${result.height||loaded.naturalHeight} px · ${spacing.toFixed(3)} m/px · ${result.tiles||1} teselas`;$('area-summary').textContent=`Centro ${Number($('lat').value).toFixed(6)}, ${Number($('lon').value).toFixed(6)} · ${$('span').value} m`;status('Ortofoto cargada. OpenCV analizará la resolución descargada; la vista muestra toda el área.');await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));}catch(error){status(error.message,true);}finally{clearInterval(progressTimer);progressTimer=null;loading(false);busy=false;controls();}
});
$('auto-detect').onclick=async()=>{
  if(busy)return;busy=true;controls();loading(true,'Analizando la ortofoto a su resolución descargada…');status('Analizando el área completa…');
  try{if($('mode').value==='segmentation')await refreshModel();const result=await api('/api/extract',{bbox,polygon:loadedPolygon,source:loadedSource,mode:$('mode').value,threshold:Number($('threshold').value)/100});cancelAnimationFrame(frame);traceHistory=[];paths=result.paths;geojson=result.geojson;setPoints([]);selected=paths.length?0:-1;visible=Infinity;detectedMask=result.mask?await maskOverlay(result.mask):null;const info=result.diagnostics;if(info){$('detection-info').textContent=`Cobertura detectada: ${info.coverage_percent}%`+(info.probability_max!==undefined?` · probabilidad máxima: ${info.probability_max.toFixed(3)}`:'');}updateCandidates();animate();status(result.message);}catch(error){status(error.message,true);}finally{loading(false);busy=false;controls();}
};
$('candidate').onchange=()=>{traceEdit=null;selected=Number($('candidate').value);setPoints([]);controls();draw();};
$('remove-candidate').onclick=()=>{if(selected<0||busy||wololoState)return;traceEdit=null;saveTrace();paths.splice(selected,1);geojson.features.splice(selected,1);setPoints([]);selected=paths.length?Math.min(selected,paths.length-1):-1;updateCandidates();status('Trazado descartado.');};
$('edit-candidate').onclick=()=>{if(selected<0)return;const line=paths[selected],count=Math.min(12,line.length);setPoints(Array.from({length:count},(_,i)=>[...line[Math.round(i*(line.length-1)/(count-1))]]));$('tool').value='correct';toolHelp();controls();draw();status('Arrastra los puntos para corregirlos y pulsa Recalcular con puntos.');};
$('undo').onclick=()=>{saveTrace();points.pop();pointIds.pop();selectedPointId=null;controls();draw();};$('clear').onclick=()=>{saveTrace();setPoints([]);controls();draw();};
$('undo-trace').onclick=()=>{if(busy||wololoState||!traceHistory.length)return;traceEdit=null;cancelAnimationFrame(frame);const previous=traceHistory.pop();paths=previous.paths;geojson=previous.geojson;points=previous.points;pointIds=previous.pointIds;selectedPointId=previous.selectedPointId;selected=previous.selected;visible=Infinity;$('simplify-info').textContent='Cambio deshecho.';updateCandidates();status('Se ha restaurado el estado anterior del trazado.');};
$('simplify-scope').onchange=controls;
$('simplify').onclick=()=>{
  if(busy||!paths.length)return;const tolerance=Number($('simplify-tolerance').value),indexes=$('simplify-scope').value==='all'?paths.map((_,i)=>i):[selected];if(indexes.some(i=>i<0))return;
  const shared=TraceGeometry.sharedVertices(paths),changes=indexes.map(i=>({index:i,line:TraceGeometry.simplify(paths[i],tolerance,bbox,shared)}));
  const before=indexes.reduce((sum,i)=>sum+paths[i].length,0),after=changes.reduce((sum,c)=>sum+c.line.length,0);
  if(before===after){$('simplify-info').textContent=`${before} puntos: esta tolerancia no elimina más vértices.`;return;}
  saveTrace();cancelAnimationFrame(frame);visible=Infinity;setPoints([]);
  changes.forEach(({index,line})=>{paths[index]=line;const feature=geojson.features[index];feature.geometry.coordinates=line.map(p=>TraceGeometry.coordinates(p,bbox));feature.properties={...feature.properties,simplification_tolerance_m:tolerance,length_m:TraceGeometry.length(feature.geometry.coordinates)};});
  updateCandidates();$('simplify-info').textContent=`${before} → ${after} puntos · tolerancia ${tolerance} m`;status('Trazado simplificado. Puedes deshacer el cambio.');
};
$('sensitivity').oninput=()=>{$('tolerance').value=$('sensitivity').value;};
$('threshold').oninput=()=>{$('threshold-value').value=(Number($('threshold').value)/100).toFixed(2);};
$('overlay').onchange=draw;
$('show-mask').onchange=draw;
$('mode').onchange=()=>{$('model-panel').hidden=false;$('auto-help').hidden=$('mode').value==='wololo';$('auto-help').textContent='Usa las probabilidades del modelo entrenado para extraer los ejes.';resetResults();setPoints([]);$('tool').value='select';toolHelp();controls();draw();};
$('upload-model').onclick=async()=>{
  const file=$('model-file').files[0];if(!file){status('Selecciona un archivo ONNX.',true);return;}if(file.size>255*1024*1024){status('El modelo supera el máximo de 255 MB de archivo.',true);return;}
  busy=true;controls();status('Validando el modelo de segmentación…');
  try{const body=new FormData();body.append('model',file);const response=await fetch('/api/model',{method:'POST',body});const result=await response.json();if(!response.ok)throw Error(result.error);showModel(result.model);await refreshEditorModels();$('model-file').value='';resetResults();status('Modelo validado. Ya puedes analizar la ortofoto.');}catch(error){status(error.message,true);}finally{busy=false;controls();}
};
$('detect').onclick=async()=>{
  if(busy)return;busy=true;controls();status('Calculando la corrección entre tus puntos…');
  try{const result=await api('/api/detect',{bbox,points,sensitivity:Number($('sensitivity').value)});saveTrace();cancelAnimationFrame(frame);if(selected>=0){paths[selected]=result.path;geojson.features[selected]=result.geojson.features[0];}else{paths.push(result.path);if(!geojson)geojson={type:'FeatureCollection',features:[]};geojson.features.push(result.geojson.features[0]);selected=paths.length-1;}visible=Infinity;updateCandidates();$('overlay').checked=true;animate();status(`Corrección aplicada · ${result.length.toLocaleString('es-ES')} m. Revisa el resultado.`);}catch(error){status(error.message,true);}finally{busy=false;controls();}
};
$('replay').onclick=()=>{$('overlay').checked=true;animate();};
function downloadFile(content,type,filename){const url=URL.createObjectURL(new Blob([content],{type}));const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function exportTraces(){return geojson?{...geojson,features:selected>=0&&geojson.features[selected]?[geojson.features[selected]]:geojson.features}:null;}
$('export').onclick=()=>{const output=exportTraces();if(output)downloadFile(JSON.stringify(output,null,2),'application/geo+json',`caminos-${loadedSource}.geojson`);};
$('export-osm').onclick=()=>{if(!geojson)return;try{downloadFile(TraceGeometry.osm(exportTraces()),'application/xml',`caminos-${loadedSource}.osm`);status('Archivo OSM exportado. Ábrelo en JOSM con Archivo → Abrir.');}catch(error){status(error.message,true);}};
function wololoCommit(){
  const state=wololoState,line=state.accepted.flatMap((s,i)=>i?s.path.slice(1):s.path);
  if(line.length<2){if(paths.length>state.resultIndex){paths.splice(state.resultIndex,1);geojson.features.splice(state.resultIndex,1);}selected=paths.length?0:-1;updateCandidates();return;}
  paths[state.resultIndex]=line;if(!geojson)geojson={type:'FeatureCollection',features:[]};
  const coordinates=line.map(p=>TraceGeometry.coordinates(p,bbox));
  geojson.features[state.resultIndex]={type:'Feature',properties:{source:loadedSource==='itacyl'?'ITACyL':'PNOA IGN',method:'wololo-guided-segmentation',review_required:true,length_m:TraceGeometry.length(coordinates)},geometry:{type:'LineString',coordinates}};
  selected=state.resultIndex;visible=Infinity;updateCandidates();
}
function wololoFocus(section){
  const xs=section.path.map(p=>p[0]),ys=section.path.map(p=>p[1]);
  const x=(Math.min(...xs)+Math.max(...xs))/2,y=(Math.min(...ys)+Math.max(...ys))/2;
  zoom=8;panX=viewWidth/2-x*1024*viewScale();panY=viewHeight/2-y*planeHeight()*viewScale();clampPan();hoverPoint=null;$('zoom-value').textContent='800%';draw();
}
function wololoNext(){
  const state=wololoState;let automatic=0;
  while(state.index<state.sections.length&&!state.sections[state.index].uncertain&&automatic<2){state.accepted.push(state.sections[state.index++]);automatic++;}
  wololoCommit();
  if(state.index>=state.sections.length){wololoState=null;wololoCorrection=false;setPoints([]);$('wololo-review').hidden=true;controls();draw();status('Wololo ha llegado al punto final. Revisa el trazado antes de exportarlo.');return;}
  const section=state.sections[state.index];$('wololo-review').hidden=false;
  $('wololo-question').textContent=section.junction?'Posible cruce o bifurcación. Confirma o corrige la dirección.':section.uncertain?`Tramo dudoso: ${Math.round(section.low_fraction*100)}% por debajo del umbral. ¿Por dónde sigue el camino?`:'Confirma la dirección del siguiente tramo antes de continuar.';
  wololoFocus(section);controls();status('Wololo espera tu revisión del tramo naranja.');
}
async function runWololo(waypoint=null){
  if(busy)return;
  const limitField=$('wololo-limit');if(!limitField.reportValidity())return;
  const searchLimit=Number(limitField.value);if(!Number.isInteger(searchLimit)){status('El límite de búsqueda debe ser un entero.',true);return;}
  const previous=wololoState;
  const start=previous?.accepted.length?previous.accepted.at(-1).path.at(-1):points[0],end=points.at(-1);
  const anchors=previous?(waypoint?[start,waypoint,end]:[start,end]):points;
  busy=true;controls();loading(true,'Wololo: analizando teselas y buscando el camino…');
  try{
    const result=await api('/api/wololo',{bbox,polygon:loadedPolygon,source:loadedSource,points:anchors,threshold:.5,search_limit:searchLimit,tolerance_m:Number($('wololo-tolerance').value)});
    if(!previous)saveTrace();
    wololoState={sections:result.sections,index:0,accepted:previous?.accepted||[],resultIndex:previous?.resultIndex??paths.length};
    $('wololo-info').textContent=`${result.diagnostics.tiles} teselas · ${result.diagnostics.computed_tiles} nuevas · sin descargar más imágenes`;
    if(result.diagnostics.centered)$('wololo-info').textContent+=` · eje central estimado · ${result.diagnostics.raw_nodes} → ${result.diagnostics.simplified_nodes} nodos · ${result.diagnostics.tolerance_m} m`;
    wololoCorrection=false;$('overlay').checked=true;cancelAnimationFrame(frame);wololoNext();
  }catch(error){wololoCorrection=true;$('tool').value='correct';toolHelp();status(error.message,true);}finally{busy=false;loading(false);controls();}
}
$('wololo-start').onclick=()=>runWololo();
$('wololo-confirm').onclick=()=>{if(busy||!wololoState)return;wololoCorrection=false;wololoState.accepted.push(wololoState.sections[wololoState.index++]);wololoNext();};
$('wololo-correct').onclick=()=>{if(!wololoState)return;wololoCorrection=true;$('tool').value='correct';toolHelp();status('Pulsa sobre el camino para indicar por dónde continuar. Se recalculará desde el último tramo aceptado.');};
$('wololo-back').onclick=()=>{if(busy||!wololoState?.accepted.length)return;const state=wololoState,undone=state.accepted.pop();state.sections=[undone,...state.sections.slice(state.index)];state.index=0;wololoCorrection=false;wololoCommit();$('wololo-review').hidden=false;$('wololo-question').textContent='Tramo deshecho. Confirma o corrige su dirección.';wololoFocus(undone);controls();};
$('wololo-finish').onclick=()=>{if(busy||!wololoState)return;wololoCommit();wololoState=null;wololoCorrection=false;setPoints([]);$('wololo-review').hidden=true;controls();draw();status('Camino finalizado en el último tramo aceptado. La propuesta pendiente se ha descartado.');};
$('wololo-reset').onclick=()=>{if(busy)return;if(wololoState)wololoCommit();wololoState=null;wololoCorrection=false;setPoints([]);$('wololo-review').hidden=true;$('tool').value='correct';toolHelp();controls();draw();status('Marcador activo: marca un nuevo inicio y fin. Los trazados aceptados se conservan.');};
toolHelp();refreshModel().catch(()=>status('No se pudo conectar con el servidor local.',true));
