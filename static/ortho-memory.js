let serverMemory=null,memorySerial=0;
function memoryEstimate(){
 const gsd=Number($('ortho-gsd').value),lat=Number($('lat').value),span=Number($('span').value);
 let width=span,height=span;
 if(requestedBBox){const b=requestedBBox,centerLat=(2*Math.atan(Math.exp((b[1]+b[3])/2/6378137))-Math.PI/2),factor=Math.cos(centerLat);width=(b[2]-b[0])*factor;height=(b[3]-b[1])*factor;}
 const pixels=Math.ceil(width/gsd)*Math.ceil(height/gsd),mp=pixels/1e6,limit=Number($('ortho-max-mp').value),bytes=pixels*(serverMemory?.bytes_per_pixel||96)+(serverMemory?.model_reserve_bytes||512*1024**2);
 $('ortho-size-estimate').textContent=`Area: ${mp.toFixed(1)} MP (${Math.ceil(width/gsd)} x ${Math.ceil(height/gsd)} px). RAM estimada: ${(bytes/1024**3).toFixed(2)} GB.`+(limit>0&&mp>limit?' Supera el limite elegido: aumenta el limite o los m/px.':'');
 $('ortho-size-estimate').classList.toggle('memory-over-limit',limit>0&&mp>limit);
}
async function refreshServerMemory(useRecommended=false){
 const serial=++memorySerial;
 try{const response=await fetch('/api/system-memory');if(!response.ok)throw Error();const data=await response.json();if(serial!==memorySerial)return;serverMemory=data;
 $('ortho-memory-info').textContent=data.available_bytes===null?'No se pudo consultar la RAM. Recomendacion provisional: 32 MP.':`Servidor: ${(data.available_bytes/1024**3).toFixed(1)} GB disponibles de ${(data.total_bytes/1024**3).toFixed(1)} GB. Recomendado: ${data.recommended_megapixels} MP.`;
 let stored=null;try{stored=localStorage.getItem('terra-ortho-max-mp');}catch{}
 if(useRecommended||stored===null){$('ortho-max-mp').value=data.recommended_megapixels;if(useRecommended)persistMemoryLimit();}else if(Number.isFinite(Number(stored))&&Number(stored)>=0)$('ortho-max-mp').value=stored;
 memoryEstimate();
 }catch{$('ortho-memory-info').textContent='No se pudo consultar la RAM del servidor. Puedes fijar el limite manualmente.';memoryEstimate();}
}
function persistMemoryLimit(){if($('ortho-max-mp').validity.valid)try{localStorage.setItem('terra-ortho-max-mp',$('ortho-max-mp').value);}catch{}memoryEstimate();}
$('ortho-max-mp').addEventListener('input',persistMemoryLimit);
$('ortho-use-recommended').onclick=()=>refreshServerMemory(true);
$('ortho-gsd').addEventListener('change',memoryEstimate);
window.addEventListener('area-picked',memoryEstimate);
refreshServerMemory();
