// Geometry editing and local JOSM export; distances use a local Mercator scale.
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.TraceGeometry=api;})(typeof globalThis!=='undefined'?globalThis:this,()=>{
 const R=6378137;
 const key=p=>p.map(n=>n.toPrecision(12)).join(',');
 function coordinates(p,bbox){const x=bbox[0]+p[0]*(bbox[2]-bbox[0]),y=bbox[3]-p[1]*(bbox[3]-bbox[1]);return [x/R*180/Math.PI,(2*Math.atan(Math.exp(y/R))-Math.PI/2)*180/Math.PI];}
 function length(coords){let sum=0;for(let i=1;i<coords.length;i++){const a=coords[i-1],b=coords[i],lat1=a[1]*Math.PI/180,lat2=b[1]*Math.PI/180,dlon=(b[0]-a[0])*Math.PI/180,v=Math.sin((lat2-lat1)/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dlon/2)**2;sum+=2*R*Math.asin(Math.min(1,Math.sqrt(v)));}return Math.round(sum*10)/10;}
 function sharedVertices(paths){const counts=new Map();paths.forEach(line=>new Set(line.map(key)).forEach(k=>counts.set(k,(counts.get(k)||0)+1)));return new Set([...counts].filter(([,count])=>count>1).map(([k])=>k));}
 function simplify(line,tolerance,bbox,protectedKeys=new Set()){
  if(!Number.isFinite(tolerance)||tolerance<=0)throw Error('La tolerancia debe ser positiva.');
  if(line.length<=2)return line.map(p=>[...p]);
  const latitude=coordinates([.5,.5],bbox)[1]*Math.PI/180,scale=Math.cos(latitude);
  const xy=line.map(([x,y])=>[x*(bbox[2]-bbox[0])*scale,y*(bbox[3]-bbox[1])*scale]);
  const keep=new Set([0,line.length-1]);line.forEach((p,i)=>{if(protectedKeys.has(key(p)))keep.add(i);});
  const closed=key(line[0])===key(line[line.length-1]);
  if(closed){let furthest=1;for(let i=2;i<line.length-1;i++)if(Math.hypot(...xy[i].map((v,j)=>v-xy[0][j]))>Math.hypot(...xy[furthest].map((v,j)=>v-xy[0][j])))furthest=i;keep.add(furthest);}
  const anchors=[...keep].sort((a,b)=>a-b),stack=anchors.slice(1).map((end,i)=>[anchors[i],end]);
  while(stack.length){const [start,end]=stack.pop(),a=xy[start],b=xy[end],dx=b[0]-a[0],dy=b[1]-a[1],denominator=dx*dx+dy*dy;let max=tolerance*tolerance,index=-1;
   for(let i=start+1;i<end;i++){const p=xy[i],t=denominator?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/denominator)):0,d=(p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2;if(d>max){max=d;index=i;}}
   if(index>=0){keep.add(index);stack.push([start,index],[index,end]);}
  }
  const result=[...keep].sort((a,b)=>a-b).map(i=>[...line[i]]);
  return closed&&new Set(result.map(key)).size<3?line.map(p=>[...p]):result;
 }
 function osm(geojson){
  const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll("'",'&apos;');
  const nodes=new Map(),ways=[];let next=-1;
  for(const feature of geojson.features){const coords=feature.geometry.coordinates;if(feature.geometry.type!=='LineString'||coords.length<2)continue;const refs=coords.map(([lon,lat])=>{if(!Number.isFinite(lon)||!Number.isFinite(lat)||Math.abs(lon)>180||Math.abs(lat)>90)throw Error('Coordenadas no válidas para OSM.');const k=`${lon.toFixed(7)},${lat.toFixed(7)}`;if(!nodes.has(k))nodes.set(k,{id:next--,lon,lat});return nodes.get(k).id;});const id=next--;ways.push(`<way id="${id}" action="modify" visible="true">${refs.map(ref=>`<nd ref="${ref}"/>`).join('')}<tag k="source" v="${escape(feature.properties?.source||'PNOA IGN')}"/><tag k="fixme" v="Revisar trazado detectado, conexiones y clasificación del camino"/></way>`);}
  if(!ways.length)throw Error('No hay trazados que exportar.');
  const all=[...nodes.values()],bounds=`<bounds minlat="${Math.min(...all.map(n=>n.lat))}" minlon="${Math.min(...all.map(n=>n.lon))}" maxlat="${Math.max(...all.map(n=>n.lat))}" maxlon="${Math.max(...all.map(n=>n.lon))}"/>`;
  return `<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="TERRA PNOA" upload="false">\n${bounds}\n${all.map(n=>`<node id="${n.id}" action="modify" visible="true" lat="${n.lat.toFixed(7)}" lon="${n.lon.toFixed(7)}"/>`).join('\n')}\n${ways.join('\n')}\n</osm>\n`;
 }
 return {coordinates,length,sharedVertices,simplify,osm};
});
