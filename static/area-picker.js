// OpenStreetMap locator; its square footprint matches the backend EPSG:3857 request.
window.areaPicker=(()=>{
  const get=id=>document.getElementById(id),dialog=get('area-dialog');
  let map=null,outline=null,marker=null,selection=null,drawing=false,start=null,pointer=null,ignoreClickUntil=0;
  let customApply=null;
  let storageContext='editor',restoring=false;
  function saved(context){try{return JSON.parse(localStorage.getItem(`terra-area-${context}`));}catch{return null;}}
  function remember(){
    if(restoring||!map||!valid(selection))return;
    const center=map.getCenter();
    try{localStorage.setItem(`terra-area-${storageContext}`,JSON.stringify({selection:{...selection},view:{lat:center.lat,lon:center.lng,zoom:map.getZoom()}}));}catch{}
  }
  function valid(s){return s&&Number.isFinite(s.lat)&&Number.isFinite(s.lon)&&Number.isFinite(s.span)&&s.lat>=27&&s.lat<=44.5&&s.lon>=-19&&s.lon<=5&&s.span>=100&&s.span<=3000&&Number.isFinite(s.height??s.span)&&(s.height??s.span)>=100&&(s.height??s.span)<=3000;}
  function bounds(s){const p=L.CRS.EPSG3857.project(L.latLng(s.lat,s.lon)),half=s.span/Math.cos(s.lat*Math.PI/180)/2,halfHeight=(s.height??s.span)/Math.cos(s.lat*Math.PI/180)/2;return L.latLngBounds(L.CRS.EPSG3857.unproject(L.point(p.x-half,p.y-halfHeight)),L.CRS.EPSG3857.unproject(L.point(p.x+half,p.y+halfHeight)));}
  function preview(){
    get('apply-area').disabled=!valid(selection);
    if(!valid(selection)){get('picker-summary').textContent='Elige una zona en España, entre 100 y 3000 m.';return;}
    const box=bounds(selection);
    if(outline)outline.setBounds(box);else outline=L.rectangle(box,{color:'#365f36',weight:2,fillOpacity:.12,interactive:false}).addTo(map);
    if(marker)marker.setLatLng([selection.lat,selection.lon]);else marker=L.circleMarker([selection.lat,selection.lon],{radius:5,color:'#365f36',fillOpacity:1,interactive:false}).addTo(map);
    get('picker-span').value=selection.span;get('picker-height').value=selection.height??selection.span;
    get('picker-summary').textContent=`${selection.lat.toFixed(6)}, ${selection.lon.toFixed(6)} · ${selection.span} × ${selection.height??selection.span} m`;
    remember();
  }
  function setDrawing(value){drawing=value;start=null;get('pick-center').classList.toggle('active',!value);get('draw-area').classList.toggle('active',value);if(value)map.dragging.disable();else map.dragging.enable();map.getContainer().style.cursor=value?'crosshair':'';get('picker-help').textContent=value?'Arrastra desde una esquina para dibujar un rectángulo (100–3000 m).':'Haz clic para elegir el centro. Arrastra el mapa para desplazarte.';}
  function square(end){
    const a=L.CRS.EPSG3857.project(start),b=L.CRS.EPSG3857.project(end),center=L.CRS.EPSG3857.unproject(L.point((a.x+b.x)/2,(a.y+b.y)/2)),factor=Math.cos(center.lat*Math.PI/180);
    selection={lat:center.lat,lon:center.lng,span:Math.max(100,Math.min(3000,Math.round(Math.abs(b.x-a.x)*factor))),height:Math.max(100,Math.min(3000,Math.round(Math.abs(b.y-a.y)*factor)))};preview();
  }
  function create(){
    map=L.map('osm-map',{center:[40.42,-4.1],zoom:15,minZoom:5,maxZoom:19,boxZoom:false});
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'}).addTo(map).on('tileerror',()=>{get('picker-help').textContent='No se pudieron cargar algunas teselas. Comprueba tu conexión; puedes usar las coordenadas manuales.';});
    L.control.scale({imperial:false}).addTo(map);
    map.on('moveend',remember);
    map.on('click',event=>{if(drawing||performance.now()<ignoreClickUntil)return;selection={...selection,lat:event.latlng.lat,lon:event.latlng.lng};preview();});
    const container=map.getContainer();
    container.addEventListener('pointerdown',event=>{
      if(!drawing||event.button!==0||event.target.closest('.leaflet-control'))return;
      event.preventDefault();pointer=event.pointerId;container.setPointerCapture(pointer);start=map.mouseEventToLatLng(event);
    });
    container.addEventListener('pointermove',event=>{if(start&&event.pointerId===pointer)square(map.mouseEventToLatLng(event));});
    container.addEventListener('pointerup',event=>{if(!start||event.pointerId!==pointer)return;square(map.mouseEventToLatLng(event));start=null;container.releasePointerCapture(pointer);pointer=null;ignoreClickUntil=performance.now()+300;setDrawing(false);});
    container.addEventListener('pointercancel',()=>{start=null;pointer=null;});
    get('pick-center').onclick=()=>setDrawing(false);get('draw-area').onclick=()=>setDrawing(true);
    get('fit-area').onclick=()=>{if(valid(selection))map.fitBounds(bounds(selection),{padding:[40,40],maxZoom:17});};
    get('picker-height').onchange=()=>{selection.height=Number(get('picker-height').value);preview();};
    get('picker-span').onchange=()=>{selection.span=Number(get('picker-span').value);preview();};
  }
  get('close-area').onclick=()=>dialog.close();
  dialog.addEventListener('close',remember);
  get('picker-generate-url').onclick=()=>{
    const center=map.getCenter();
    get('picker-osm-url').value=`https://www.openstreetmap.org/#map=${map.getZoom()}/${center.lat.toFixed(6)}/${center.lng.toFixed(6)}`;
    get('picker-osm-url').focus();get('picker-osm-url').select();
    get('picker-url-status').textContent='Enlace generado de la vista actual. Puedes copiarlo.';
  };
  function applyLink(){
    const status=get('picker-url-status');
    try{
      const url=new URL(get('picker-osm-url').value.trim());
      if(!['http:','https:'].includes(url.protocol)||!['openstreetmap.org','www.openstreetmap.org'].includes(url.hostname))throw Error('Pega un enlace de openstreetmap.org.');
      const match=url.hash.match(/(?:^#|&)map=(\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)(?:&|$)/);
      if(!match)throw Error('El enlace debe contener #map=zoom/latitud/longitud.');
      const zoom=Number(match[1]),next={...selection,lat:Number(match[2]),lon:Number(match[3])};
      if(!valid(next))throw Error('Elige coordenadas dentro del área de España cubierta por los servicios de ortofotos.');
      selection=next;setDrawing(false);map.setView([selection.lat,selection.lon],Math.max(5,Math.min(19,zoom)),{animate:false});preview();
      status.textContent='Zona localizada. Ajusta el ancho o dibuja el área y pulsa «Usar esta área».';
    }catch(error){status.textContent=error.message;}
  }
  get('picker-open-url').onclick=applyLink;
  get('picker-osm-url').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();applyLink();}});
  get('picker-osm-url').addEventListener('paste',()=>setTimeout(applyLink,0));
  get('apply-area').onclick=()=>{
    if(!valid(selection))return;
    if(customApply){const callback=customApply;customApply=null;dialog.close();callback({...selection});return;}
    get('lat').value=selection.lat.toFixed(6);get('lon').value=selection.lon.toFixed(6);get('span').value=selection.span;
    dialog.close();window.dispatchEvent(new CustomEvent('area-picked',{detail:{...selection}}));
  };
  function open(options={}){
    if(typeof L==='undefined'){get('area-summary').textContent='No se pudo iniciar el mapa. Usa las coordenadas manuales.';return;}
    remember();restoring=true;
    storageContext=options.context||(options.onApply?'dataset':'editor');
    const stored=saved(storageContext);
    customApply=options.onApply||null;
    selection=valid(stored?.selection)?{...stored.selection}:options.initial||{lat:Number(get('lat').value),lon:Number(get('lon').value),span:Number(get('span').value)};
    if(!valid(selection))selection={lat:40.42,lon:-4.1,span:750};
    const firstOpen=!map;
    dialog.showModal();if(firstOpen)create();setDrawing(false);
    get('picker-url-status').textContent='';
    requestAnimationFrame(()=>{
      map.invalidateSize({animate:false});preview();
      const view=stored?.view;
      if(view&&[view.lat,view.lon,view.zoom].every(Number.isFinite)&&Math.abs(view.lat)<85&&Math.abs(view.lon)<=180&&view.zoom>=5&&view.zoom<=19)map.setView([view.lat,view.lon],view.zoom,{animate:false});
      else map.fitBounds(bounds(selection),{padding:[50,50],maxZoom:17,animate:false});
      restoring=false;remember();
    });
  }
  const initial=saved('editor');
  if(valid(initial?.selection)){get('lat').value=initial.selection.lat;get('lon').value=initial.selection.lon;get('span').value=initial.selection.span;}
  return {open,saved,bounds};
})();
