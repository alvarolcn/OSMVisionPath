function editedFeature(line,original){
 const coordinates=line.map(point=>TraceGeometry.coordinates(point,bbox));
 return {type:'Feature',properties:{...original?.properties,review_required:true,manually_edited:true,length_m:TraceGeometry.length(coordinates)},geometry:{type:'LineString',coordinates}};
}
function editDone(text){traceEdit=null;setPoints([]);cancelAnimationFrame(frame);visible=Infinity;updateCandidates();status(text);}
function joinTrace(){
 if(busy||areaDirty||wololoState||selected<0||paths.length<2)return;
 if(traceEdit?.mode==='join'&&traceEdit.second!==undefined){
  const {first,second,a,b,bridge}=traceEdit,line=[...a,...bridge.slice(1,-1),...b].filter((point,index,all)=>index===0||Math.hypot(point[0]-all[index-1][0],point[1]-all[index-1][1])>1e-9);
  saveTrace();const keep=Math.min(first,second),remove=Math.max(first,second),feature=editedFeature(line,geojson.features[first]);
  paths[keep]=line;geojson.features[keep]=feature;paths.splice(remove,1);geojson.features.splice(remove,1);selected=keep;
  editDone('Trazados unidos. Puedes deshacer la unión.');return;
 }
 traceEdit={mode:'join',first:selected};$('tool').value='select';controls();draw();
 status('Pulsa el segundo trazado. Después añade puntos a la conexión si hace falta y pulsa C para unir. Esc cancela.');
}
function traceEditClick(at){
 if(traceEdit.mode==='split'){
  const index=traceEdit.first,line=paths[index];if(nearest(at)!==index){status('Pulsa sobre el trazado seleccionado para dividirlo.');return;}
  let best=null;
  for(let i=1;i<line.length;i++){const a=line[i-1],b=line[i],dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((at[0]-a[0])*dx+(at[1]-a[1])*dy)/(dx*dx+dy*dy||1))),p=[a[0]+t*dx,a[1]+t*dy],distance=Math.hypot(p[0]-at[0],p[1]-at[1]);if(!best||distance<best.distance)best={i,p,distance};}
  if(!best)return;
  const same=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1])<1e-9;
  const left=line.slice(0,best.i),right=line.slice(best.i);if(!same(left.at(-1),best.p))left.push(best.p);if(!same(right[0],best.p))right.unshift(best.p);
  if(left.length<2||right.length<2){status('Elige un punto interior; no se puede dividir en un extremo.');return;}
  saveTrace();const original=geojson.features[index];paths.splice(index,1,left,right);geojson.features.splice(index,1,editedFeature(left,original),editedFeature(right,original));selected=index;editDone('Trazado dividido en dos. Puedes deshacer el corte.');return;
 }
 if(traceEdit.second===undefined){
  const second=nearest(at),first=traceEdit.first;if(second<0||second===first){status('Selecciona un trazado distinto para unirlo.');return;}
  let best=null;
  for(const reverseA of [false,true])for(const reverseB of [false,true]){const a=reverseA?[...paths[first]].reverse():[...paths[first]],b=reverseB?[...paths[second]].reverse():[...paths[second]],d=Math.hypot(a.at(-1)[0]-b[0][0],a.at(-1)[1]-b[0][1]);if(!best||d<best.d)best={a,b,d};}
  Object.assign(traceEdit,{second,a:best.a,b:best.b,bridge:[best.a.at(-1),best.b[0]]});
  const gap=TraceGeometry.length([TraceGeometry.coordinates(best.a.at(-1),bbox),TraceGeometry.coordinates(best.b[0],bbox)]);
  if(gap<=5){joinTrace();return;}
  status('Conexión naranja propuesta entre los extremos más próximos. Pulsa en el mapa para añadir puntos intermedios y C para confirmar. Esc cancela.');draw();
 }else{traceEdit.bridge.splice(traceEdit.bridge.length-1,0,at);draw();status('Punto añadido a la conexión. Pulsa C para unir o Esc para cancelar.');}
}
$('delete-trace').onclick=()=>$('remove-candidate').click();
$('split-trace').onclick=()=>{if(busy||areaDirty||wololoState||selected<0)return;traceEdit={mode:'split',first:selected};$('tool').value='select';controls();status('Pulsa el lugar del trazado seleccionado donde quieres dividirlo. Esc cancela.');};
$('join-traces').onclick=joinTrace;
document.addEventListener('keydown',event=>{
 if($('editor-view').hidden||busy||areaDirty||wololoState||event.target.closest('input,select,textarea,[contenteditable],dialog')||!(event.ctrlKey||event.metaKey)||event.shiftKey||event.key.toLowerCase()!=='z')return;
 event.preventDefault();
 if(traceEdit){if(traceEdit.bridge?.length>2){traceEdit.bridge.splice(-2,1);draw();status('Último punto de conexión deshecho.');}else{traceEdit=null;controls();draw();status('Edición pendiente cancelada.');}return;}
 $('undo-trace').click();
});
