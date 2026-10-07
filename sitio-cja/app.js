/* Sitio "Tu marca en la luz" — Comisión de Jóvenes Arquitectos · Jujuy
   Motor 3D en canvas (sin dependencias) + selector de lugares. Los datos viven en content/lugares.js */
(function(){
  const D=window.CJA; if(!D){console.error('Falta content/lugares.js');return;}
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $=id=>document.getElementById(id);
  const byN=new Map(D.lugares.map(l=>[l.n,l]));
  const taken=l=>l.estado!=='disponible';

  /* ---------- Cabecera: datos ---------- */
  const disp=D.lugares.filter(l=>!taken(l)).length;
  $('statDisp').textContent=`${disp} de ${D.lugares.length}`;
  $('statCierre').textContent=D.evento.cierreReservas; $('statFechas').textContent=D.evento.fechas;
  $('pillText').textContent=`Reservas abiertas · ${disp} lugares disponibles`;
  $('cMail').textContent=D.contacto.email; $('cMail').href='mailto:'+D.contacto.email;
  $('cWa').textContent=D.contacto.telefono; $('cWa').href='https://wa.me/'+D.contacto.whatsapp;
  $('cIg').textContent='@'+D.contacto.instagram; $('cIg').href='https://www.instagram.com/'+D.contacto.instagram;
  $('cWeb').textContent=D.contacto.web; $('cWeb').href='https://'+D.contacto.web;

  /* ---------- Geometría (metros) ---------- */
  // Según el modelo SketchUp: tarima 3×3, hilos desde el perímetro que convergen con giro en un cuello
  // angosto bajo el marco; marco superior 1,50×1,50 con diagonales en X, colgado de un cable entre los dos postes.
  const B=1.5, T=0.75, Z0=0.10, POST=4.0, PD=2.35, N=26;
  const NECK_R=0.16, NECK_Z=2.95, H=3.35, HANG_Z=3.92, TW=0.36;
  function perim(u,s,rot,z){u=((u%1)+1)%1;const k=u*4,side=Math.floor(k),f=k-side;let x,y;
    if(side===0){x=-s+2*s*f;y=-s}else if(side===1){x=s;y=-s+2*s*f}else if(side===2){x=s-2*s*f;y=s}else{x=-s;y=s-2*s*f}
    const c=Math.cos(rot),sn=Math.sin(rot);return [x*c-y*sn,x*sn+y*c,z];}
  const neckPt=u=>[NECK_R*Math.cos(2*Math.PI*u),NECK_R*Math.sin(2*Math.PI*u),NECK_Z];
  const strings=[];for(let side=0;side<4;side++)for(let i=0;i<N;i++){const u=(side+i/N)/4;strings.push([perim(u,B,0,Z0),neckPt(u+TW)]);}
  const sq=(s,rot,z)=>[0,.25,.5,.75].map(u=>perim(u,s,rot,z));
  const base=sq(B,0,Z0),baseLow=sq(B,0,0),top=sq(T,Math.PI/4,H);
  const posts=[[PD,-PD],[-PD,PD]];
  const quadXZ=(x0,x1,y,z0,z1)=>[[x0,y,z0],[x1,y,z0],[x1,y,z1],[x0,y,z1]];
  const lerp3=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
  const subQuad=(c,u0,u1,v0,v1)=>{const b0=lerp3(c[0],c[1],u0),b1=lerp3(c[0],c[1],u1),t0=lerp3(c[3],c[2],u0),t1=lerp3(c[3],c[2],u1);return [lerp3(b0,t0,v0),lerp3(b1,t1,v0),lerp3(b1,t1,v1),lerp3(b0,t0,v1)];};
  const center=c=>[(c[0][0]+c[2][0])/2,(c[0][1]+c[2][1])/2,(c[0][2]+c[2][2])/2];
  // Banners
  const BAN={
    izq:{c:quadXZ(-3.95,-3.10,-1.0,0.05,2.25),vert:true,slots:[1,2,3]},
    der:{c:quadXZ(3.10,3.95,-1.0,0.05,2.25),vert:true,slots:[4,5,6]},
    fondo:{c:quadXZ(-2.0,2.0,3.6,0.7,1.9),vert:false,slots:[7,8,9,10]}
  };
  // Lugares: cuadrilátero 3D de cada uno (para pintar y para el marcador)
  const SPOT={};
  for(const id in BAN){const b=BAN[id],n=b.slots.length;b.slots.forEach((num,i)=>{let q;
    if(b.vert){const h=0.82/n,v1=0.85-i*h,v0=v1-h+0.035;q=subQuad(b.c,0.08,0.92,v0,v1);}
    else{const w=0.94/n,u0=0.03+i*w,u1=u0+w-0.02;q=subQuad(b.c,u0,u1,0.12,0.78);}
    SPOT[num]={q,anchor:center(q),kind:'banner'};});}
  // postes: vinilo envolvente (franja 0,32 × 2,00 desde 1,2 m)
  SPOT[11]={q:null,anchor:[PD,-PD,2.2],kind:'post',post:[PD,-PD]};
  SPOT[12]={q:null,anchor:[-PD,PD,2.2],kind:'post',post:[-PD,PD]};
  // franja frontal de tarima
  SPOT[13]={q:[[-B,-B,0],[B,-B,0],[B,-B,Z0],[-B,-B,Z0]],anchor:[0,-B,Z0/2],kind:'strip'};
  // extras: anclados a un costado (láminas y remeras no están sobre la obra)
  SPOT[14]={q:null,anchor:[-4.4,3.3,1.3],kind:'float'};
  SPOT[15]={q:null,anchor:[4.4,3.3,1.0],kind:'float'};

  /* ---------- Canvas ---------- */
  const cv=$('cv'),ctx=cv.getContext('2d'),stage=$('stage');
  let W=800,Hh=640,dpr=1;
  function resize(){const r=stage.getBoundingClientRect();dpr=Math.min(2,window.devicePixelRatio||1);W=Math.max(300,Math.round(r.width));Hh=Math.max(240,Math.round(r.height));cv.width=W*dpr;cv.height=Hh*dpr;}
  resize(); if('ResizeObserver' in window) new ResizeObserver(resize).observe(stage); else addEventListener('resize',resize);
  let night=false,theta=0.65,phi=0.42,drag=null,auto=!reduce,target=null,t0=performance.now();
  const VIEWS={foto:{theta:0.10,phi:0.30},atras:{theta:Math.PI+0.15,phi:0.34}};
  function view(p){const [x,y,z]=p;const c=Math.cos(theta),s=Math.sin(theta);const xr=x*c-y*s,yr=x*s+y*c;const cp=Math.cos(phi),sp=Math.sin(phi);const yv=yr*cp-z*sp,zv=yr*sp+z*cp;const d=12,f=Math.min(W,Hh*1.3)*1.08/(d+yv);return [W/2+xr*f,Hh*0.72-zv*f,yv];}
  const proj=view;
  const line=(a,b)=>{const p=proj(a),q=proj(b);ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);};
  const poly=pts=>{const p=pts.map(proj);ctx.moveTo(p[0][0],p[0][1]);for(let i=1;i<p.length;i++)ctx.lineTo(p[i][0],p[i][1]);ctx.closePath();};
  const path2=P=>{ctx.moveTo(P[0][0],P[0][1]);for(let i=1;i<P.length;i++)ctx.lineTo(P[i][0],P[i][1]);ctx.closePath();};
  const sel=new Set(); let focus=null; const markers=[];

  function spotFill(num){const l=byN.get(num);if(sel.has(num))return 'rgba(200,19,94,.16)';if(l.estado==='confirmado')return 'rgba(27,26,25,.10)';if(l.estado==='reservado')return 'rgba(201,138,18,.16)';return 'rgba(27,26,25,.035)';}
  function spotStroke(num){const l=byN.get(num);if(sel.has(num)||focus===num)return '#C8135E';if(l.estado==='reservado')return '#C98A12';if(l.estado==='confirmado')return '#1B1A19';return 'rgba(27,26,25,.35)';}
  function labelFor(num){const l=byN.get(num);return l.sponsor||(l.estado==='disponible'?'':l.estado.toUpperCase());}

  function drawStructure(now){
    const pulse=night?0.75+0.25*Math.sin((now-t0)/900):1;
    ctx.beginPath();poly(baseLow);poly(base);for(let i=0;i<4;i++)line(baseLow[i],base[i]);
    ctx.lineWidth=1;ctx.strokeStyle=night?'rgba(180,215,255,.35)':'rgba(27,26,25,.55)';ctx.stroke();
    ctx.fillStyle=night?'rgba(63,166,242,.08)':'rgba(27,26,25,.05)';ctx.beginPath();poly(base);ctx.fill();
    // franja frontal (lugar 13)
    const S=SPOT[13].q.map(proj);ctx.beginPath();path2(S);ctx.fillStyle=byN.get(13).sponsor||sel.has(13)||focus===13?spotFill(13):'rgba(200,19,94,.0)';ctx.fill();ctx.lineWidth=1;ctx.strokeStyle=spotStroke(13);ctx.stroke();
    // postes (+ vinilos 11 y 12)
    posts.forEach(([x,y],i)=>{const num=i===0?11:12;ctx.beginPath();line([x,y,0],[x,y,POST]);ctx.lineWidth=Math.max(3,W*0.007);ctx.strokeStyle=night?'#1b2740':'#2b2a28';ctx.stroke();
      ctx.beginPath();line([x,y,1.2],[x,y,3.2]);ctx.lineWidth=Math.max(5,W*0.011);ctx.strokeStyle=sel.has(num)||focus===num?'#C8135E':(byN.get(num).estado==='reservado'?'#C98A12':(byN.get(num).estado==='confirmado'?'#4a4642':(night?'#243352':'#d9d4cb')));ctx.stroke();});
    // cable entre postes (pasa sobre el centro), tensor colgante y riendas a tierra
    ctx.beginPath();ctx.lineWidth=1;ctx.setLineDash([4,5]);
    line([PD,-PD,POST],[0,0,HANG_Z]);line([0,0,HANG_Z],[-PD,PD,POST]);line([0,0,HANG_Z],[0,0,H]);
    line([PD,-PD,POST],[PD*1.6,-PD*1.6,0]);line([-PD,PD,POST],[-PD*1.6,PD*1.6,0]);
    ctx.strokeStyle=night?'rgba(180,215,255,.35)':'rgba(27,26,25,.45)';ctx.stroke();ctx.setLineDash([]);
    // hilos: del perímetro de la tarima al cuello, con giro
    ctx.beginPath();strings.forEach(([a,b])=>line(a,b));
    if(night){ctx.shadowColor=`rgba(63,166,242,${0.9*pulse})`;ctx.shadowBlur=14;ctx.strokeStyle=`rgba(190,228,255,${0.55+0.3*pulse})`;ctx.lineWidth=1;}
    else{ctx.strokeStyle='rgba(27,26,25,.42)';ctx.lineWidth=0.8;}
    ctx.stroke();ctx.shadowBlur=0;
    // cuello: haz de hilos que sube hasta el marco
    const nA=proj([0,0,NECK_Z]),nB=proj([0,0,H]);const c0=Math.cos(theta),s0=Math.sin(theta);
    const wA=Math.hypot(...((p,q)=>[p[0]-q[0],p[1]-q[1]])(proj([NECK_R*c0,-NECK_R*s0,NECK_Z]),proj([-NECK_R*c0,NECK_R*s0,NECK_Z])));
    ctx.beginPath();ctx.moveTo(nA[0],nA[1]);ctx.lineTo(nB[0],nB[1]);ctx.lineWidth=Math.max(3,wA);ctx.lineCap='butt';
    if(night){ctx.shadowColor=`rgba(120,200,255,${pulse})`;ctx.shadowBlur=18;ctx.strokeStyle=`rgba(200,232,255,${0.7+0.2*pulse})`;}else{ctx.strokeStyle='rgba(27,26,25,.75)';}
    ctx.stroke();ctx.shadowBlur=0;
    // tarima iluminada y marco superior con diagonales en X
    ctx.beginPath();poly(base);poly(top);line(top[0],top[2]);line(top[1],top[3]);
    if(night){ctx.shadowColor=`rgba(120,200,255,${pulse})`;ctx.shadowBlur=22;ctx.strokeStyle='#eaf6ff';ctx.lineWidth=2.4;}
    else{ctx.strokeStyle='#1B1A19';ctx.lineWidth=2.2;}
    ctx.stroke();ctx.shadowBlur=0;
    const p0=proj([0.4,0.2,Z0]),p1=proj([0.4,0.2,Z0+1.7]);
    ctx.beginPath();ctx.moveTo(p0[0],p0[1]);ctx.lineTo(p1[0],p1[1]);ctx.lineWidth=2.5;ctx.strokeStyle=night?'#0a0f1c':'#C8135E';ctx.stroke();
    ctx.beginPath();ctx.arc(p1[0],p1[1]-6,5,0,Math.PI*2);ctx.fillStyle=night?'#0a0f1c':'#C8135E';ctx.fill();
  }
  function drawBanner(id){
    const b=BAN[id],c=b.c,P=c.map(proj);
    ctx.beginPath();
    if(b.vert){const m=center(c);line([m[0],m[1],0],[m[0],m[1],c[3][2]+0.1]);const foot=subQuad(c,-0.1,1.1,0,0);line(foot[0],foot[1]);}
    else{line([c[0][0],c[0][1],0],[c[0][0],c[0][1],c[3][2]+0.15]);line([c[1][0],c[1][1],0],[c[1][0],c[1][1],c[3][2]+0.15]);}
    ctx.lineWidth=2;ctx.strokeStyle=night?'#2a3654':'#2b2a28';ctx.stroke();
    ctx.beginPath();path2(P);ctx.fillStyle=night?'rgba(236,241,250,.94)':'#ffffff';ctx.fill();
    ctx.lineWidth=1.2;ctx.strokeStyle=night?'rgba(180,215,255,.55)':'rgba(27,26,25,.5)';ctx.stroke();
    const band=subQuad(c,0,1,b.vert?0.88:0.84,1).map(proj);ctx.beginPath();path2(band);ctx.fillStyle='#C8135E';ctx.fill();
    const bc=[(band[0][0]+band[2][0])/2,(band[0][1]+band[2][1])/2],bh=Math.abs(band[3][1]-band[0][1]);
    ctx.fillStyle='#fff';ctx.font=`700 ${Math.max(7,bh*0.6)}px Jost, sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('cja',bc[0],bc[1]);
    b.slots.forEach(num=>{const Q=SPOT[num].q.map(proj);ctx.beginPath();path2(Q);ctx.fillStyle=spotFill(num);ctx.fill();
      const l=byN.get(num);ctx.setLineDash(l.sponsor||sel.has(num)?[]:[3,3]);ctx.lineWidth=sel.has(num)||focus===num?2:1;ctx.strokeStyle=spotStroke(num);ctx.stroke();ctx.setLineDash([]);
      const cx=(Q[0][0]+Q[2][0])/2,cy=(Q[0][1]+Q[2][1])/2,hpx=Math.abs(Q[3][1]-Q[0][1]),wpx=Math.abs(Q[1][0]-Q[0][0]);
      const label=labelFor(num);if(!label)return;let fs=Math.min(hpx*0.3,wpx/(label.length*0.62));fs=Math.max(5,fs);
      ctx.font=`${l.sponsor?'600':'500'} ${fs}px Jost, sans-serif`;ctx.fillStyle=l.sponsor?'#1B1A19':'rgba(27,26,25,.4)';ctx.fillText(label,cx,cy);});
    ctx.textAlign='left';ctx.textBaseline='alphabetic';
  }
  function drawMarkers(){
    markers.length=0;
    const r=Math.max(11,Math.min(16,W*0.022));
    const list=D.lugares.map(l=>{const a=SPOT[l.n].anchor;const p=proj(a);return {n:l.n,x:p[0],y:p[1],d:p[2],l};}).sort((a,b)=>b.d-a.d);
    list.forEach(m=>{
      const isSel=sel.has(m.n),isF=focus===m.n;
      if(SPOT[m.n].kind==='float'){ctx.beginPath();ctx.setLineDash([3,4]);ctx.moveTo(m.x,m.y+r);ctx.lineTo(m.x,proj([SPOT[m.n].anchor[0],SPOT[m.n].anchor[1],0])[1]);ctx.strokeStyle=night?'rgba(159,176,208,.6)':'rgba(107,103,98,.6)';ctx.lineWidth=1;ctx.stroke();ctx.setLineDash([]);}
      let fill='#fff',stroke='#1B1A19',color='#1B1A19';
      if(m.l.estado==='reservado'){fill='#C98A12';stroke='#C98A12';color='#fff';}
      if(m.l.estado==='confirmado'){fill='#1B1A19';stroke='#1B1A19';color='#fff';}
      if(isSel){fill='#C8135E';stroke='#C8135E';color='#fff';}
      ctx.beginPath();ctx.arc(m.x,m.y,r+(isF?3:0),0,Math.PI*2);
      if(isF||isSel){ctx.shadowColor='rgba(200,19,94,.5)';ctx.shadowBlur=12;}
      ctx.fillStyle=fill;ctx.fill();ctx.shadowBlur=0;ctx.lineWidth=2;ctx.strokeStyle=stroke;ctx.stroke();
      ctx.fillStyle=color;ctx.font=`700 ${r*0.95}px Jost, sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(m.n),m.x,m.y+0.5);
      markers.push({n:m.n,x:m.x,y:m.y,r:r+4});
    });
    ctx.textAlign='left';ctx.textBaseline='alphabetic';
  }
  function draw(now){
    if(target){theta+=(target.theta-theta)*0.08;phi+=(target.phi-phi)*0.08;if(Math.abs(target.theta-theta)<0.002&&Math.abs(target.phi-phi)<0.002){theta=target.theta;phi=target.phi;target=null;}}
    else if(auto&&!drag)theta+=0.0022;
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,Hh);
    const pulse=night?0.75+0.25*Math.sin((now-t0)/900):1;
    ctx.lineWidth=1;ctx.setLineDash([]);ctx.strokeStyle=night?'rgba(63,166,242,.10)':'rgba(27,26,25,.08)';
    ctx.beginPath();for(let g=-5;g<=5;g++){line([g,-5,0],[g,5,0]);line([-5,g,0],[5,g,0]);}ctx.stroke();
    if(night){const c=proj([0,0,0]);const rg=ctx.createRadialGradient(c[0],c[1],10,c[0],c[1],W*0.42);rg.addColorStop(0,`rgba(63,166,242,${0.35*pulse})`);rg.addColorStop(1,'rgba(63,166,242,0)');ctx.fillStyle=rg;ctx.beginPath();ctx.ellipse(c[0],c[1],W*0.42,W*0.16,0,0,Math.PI*2);ctx.fill();}
    const items=[{d:view([0,0,1.2])[2],f:()=>drawStructure(now)}];
    for(const id in BAN)items.push({d:view(center(BAN[id].c))[2],f:()=>drawBanner(id)});
    items.sort((a,b)=>b.d-a.d).forEach(it=>it.f());
    drawMarkers();
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  /* ---------- Interacción canvas ---------- */
  const pos=e=>{const r=cv.getBoundingClientRect();return [(e.clientX-r.left)*W/r.width,(e.clientY-r.top)*Hh/r.height];};
  cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,th:theta,ph:phi,moved:false};cv.setPointerCapture(e.pointerId);});
  cv.addEventListener('pointermove',e=>{if(drag){if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>4){drag.moved=true;auto=false;target=null;setView(null);}theta=drag.th+(e.clientX-drag.x)*0.01;phi=Math.max(0.1,Math.min(1.2,drag.ph+(e.clientY-drag.y)*0.005));return;}
    const p=pos(e);const m=[...markers].reverse().find(k=>Math.hypot(k.x-p[0],k.y-p[1])<=k.r);cv.style.cursor=m?'pointer':'grab';});
  cv.addEventListener('pointerup',e=>{if(drag&&!drag.moved){const p=pos(e);const m=[...markers].reverse().find(k=>Math.hypot(k.x-p[0],k.y-p[1])<=k.r);if(m)toggleSpot(m.n,true);}drag=null;});
  cv.addEventListener('pointercancel',()=>drag=null);
  const bD=$('btnDay'),bN=$('btnNight'),mode=$('stageMode');
  function setNight(v){night=v;stage.classList.toggle('night',v);bD.setAttribute('aria-pressed',String(!v));bN.setAttribute('aria-pressed',String(v));mode.textContent=v?'Experiencia lumínica':'Elemento escultórico';}
  bD.addEventListener('click',()=>setNight(false));bN.addEventListener('click',()=>setNight(true));
  if(!reduce)setTimeout(()=>setNight(true),3000);
  const viewBtns=[...document.querySelectorAll('[data-view]')];
  function setView(name){viewBtns.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===name)));
    if(name==='giro'){auto=true;target=null;return;}
    if(!name)return;auto=false;const v=VIEWS[name];const d=((v.theta-theta)%(2*Math.PI)+3*Math.PI)%(2*Math.PI)-Math.PI;target={theta:theta+d,phi:v.phi};if(reduce){theta=target.theta;phi=target.phi;target=null;}}
  viewBtns.forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
  setView('giro');

  /* ---------- Panel: zonas, lista, detalle, selección ---------- */
  const zoneTabs=$('zoneTabs'),list=$('spotList'),detail=$('detail');
  let zone='all';
  const zones=[['all','Todos'],...Object.entries(D.zonas).map(([k,z])=>[k,z.nombre.replace('Banner ','').replace('lateral ','lat. ')])];
  zones.forEach(([k,label])=>{const b=document.createElement('button');b.type='button';b.role='tab';b.textContent=label;b.setAttribute('aria-selected',String(k===zone));b.addEventListener('click',()=>{zone=k;zoneTabs.querySelectorAll('button').forEach(x=>x.setAttribute('aria-selected',String(x===b)));renderList();});zoneTabs.appendChild(b);});
  function renderList(){list.innerHTML='';D.lugares.filter(l=>zone==='all'||l.zona===zone).forEach(l=>{
    const li=document.createElement('li');const b=document.createElement('button');b.type='button';b.className='spot '+l.estado+(sel.has(l.n)?' sel':'')+(taken(l)?' taken':'');b.id='spot-'+l.n;
    b.innerHTML=`<span class="n">${l.n}</span><span><b>${l.nombre}<span class="tier ${l.tier}">${l.tier}</span></b><small>${taken(l)?(l.estado==='confirmado'?'Confirmado':'Reservado')+(l.sponsor?' · '+l.sponsor:''):l.medida+' · '+D.zonas[l.zona].foto}</small></span><span class="price">${taken(l)?'—':l.precio}<small>${taken(l)?'':l.paquete}</small></span>`;
    b.addEventListener('click',()=>toggleSpot(l.n,false));b.addEventListener('mouseenter',()=>focus=l.n);b.addEventListener('mouseleave',()=>{if(focus===l.n)focus=null;});
    li.appendChild(b);list.appendChild(li);});}
  function toggleSpot(n,fromCanvas){const l=byN.get(n);focus=n;showDetail(n);
    if(taken(l)){return;}
    if(sel.has(n))sel.delete(n);else sel.add(n);
    renderList();renderCart();
    if(fromCanvas){const el=$('spot-'+n);if(el&&!reduce)el.scrollIntoView({block:'nearest',behavior:'smooth'});}}
  function showDetail(n){const l=byN.get(n),z=D.zonas[l.zona];detail.hidden=false;
    detail.innerHTML=`<div class="top"><span class="n">${l.n}</span><h3>${l.nombre}</h3><span class="tier ${l.tier}">${l.tier}</span></div>
      <dl class="meta"><dt>Zona</dt><dd>${z.nombre}</dd><dt>Medida</dt><dd>${l.medida}</dd><dt>Dónde</dt><dd>${z.donde}</dd><dt>En la foto</dt><dd>${z.foto}</dd><dt>Estado</dt><dd>${taken(l)?(l.estado==='confirmado'?'Confirmado':'Reservado')+(l.sponsor?' · '+l.sponsor:''):'Disponible · '+l.precio+' ('+l.paquete+')'}</dd></dl>
      <div class="acts">${taken(l)?`<button type="button" class="btn ghost" data-close>Ver otro lugar</button>`:`<button type="button" class="btn" data-toggle="${l.n}">${sel.has(l.n)?'Quitar de mi selección':'Agregar a mi selección'}</button><button type="button" class="btn ghost" data-close>Cerrar</button>`}</div>`;
    detail.querySelector('[data-close]').addEventListener('click',()=>{detail.hidden=true;focus=null;});
    const t=detail.querySelector('[data-toggle]');if(t)t.addEventListener('click',()=>toggleSpot(l.n,false));}
  const cartCount=$('cartCount'),cartTotal=$('cartTotal'),cartGo=$('cartGo');
  function parseM(s){const m=/\$\s*([\d.,]+)\s*M/i.exec(s||'');return m?parseFloat(m[1].replace(',','.')):0;}
  function renderCart(){const arr=[...sel].sort((a,b)=>a-b);cartCount.textContent=arr.length?`${arr.length} ${arr.length===1?'lugar':'lugares'} · N.º ${arr.join(', ')}`:'0 lugares';
    const tot=arr.reduce((s,n)=>s+parseM(byN.get(n).precio),0);cartTotal.textContent=arr.length?`Desde $${tot%1?tot.toFixed(1):tot} M`:'—';cartGo.disabled=!arr.length;compose();}
  cartGo.addEventListener('click',()=>{$('reservar').scrollIntoView({behavior:reduce?'auto':'smooth'});setTimeout(()=>$('empresa').focus({preventScroll:true}),reduce?0:500);});

  /* ---------- Mensaje de reserva ---------- */
  const msg=$('msg'),empresa=$('empresa'),sendMail=$('sendMail'),sendWa=$('sendWa');
  function compose(){const arr=[...sel].sort((a,b)=>a-b);const emp=empresa.value.trim();
    let t=`Hola, Comisión de Jóvenes Arquitectos.\n\n`;
    t+=emp?`Somos ${emp} y queremos `:`Queremos `;
    t+=arr.length?`reservar ${arr.length===1?'el lugar':'los lugares'} ${arr.map(n=>`${n} (${byN.get(n).nombre})`).join(', ')} en la estructura de luz de la Semana de la Arquitectura.`:`consultar por un lugar en la estructura de luz de la Semana de la Arquitectura.`;
    t+=`\n\n¿Nos confirman disponibilidad y los pasos para el logo y el aporte?\n\nGracias.`;
    msg.value=t;const subj='Reserva de lugar · '+D.evento.proyecto+(emp?' · '+emp:'');
    sendMail.href=`mailto:${D.contacto.email}?subject=${encodeURIComponent(subj)}&body=${encodeURIComponent(t)}`;
    sendWa.href=`https://wa.me/${D.contacto.whatsapp}?text=${encodeURIComponent(t)}`;}
  empresa.addEventListener('input',compose);msg.addEventListener('input',()=>{sendMail.href=`mailto:${D.contacto.email}?subject=${encodeURIComponent('Reserva de lugar · '+D.evento.proyecto)}&body=${encodeURIComponent(msg.value)}`;sendWa.href=`https://wa.me/${D.contacto.whatsapp}?text=${encodeURIComponent(msg.value)}`;});
  $('composer').addEventListener('submit',e=>{e.preventDefault();const ok=$('okMsg');const done=()=>{ok.hidden=false;setTimeout(()=>ok.hidden=true,3000);};
    if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(msg.value).then(done).catch(()=>{msg.select();done();});else{msg.select();done();}});

  renderList();renderCart();

  /* ---------- Nav activo ---------- */
  const links=[...document.querySelectorAll('.nav ul a')];
  if('IntersectionObserver' in window){const so=new IntersectionObserver(es=>es.forEach(x=>{if(x.isIntersecting)links.forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+x.target.id));}),{rootMargin:'-35% 0px -55% 0px'});
    links.forEach(a=>{const s=document.querySelector(a.getAttribute('href'));if(s)so.observe(s);});}
})();
