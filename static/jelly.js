/* REDFLAG ambient jellyfish — a lighter version of the landing-page creature,
   drawn on a fixed background canvas behind the app screens. Needs three.js r128. */
(function(){
  const canvas = document.getElementById('jelly');
  if (!canvas || !window.THREE) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.z = 10;

  const jelly = new THREE.Group(); scene.add(jelly);
  const U = { uPulse:{value:0}, uTime:{value:0} };
  const vert = `
    uniform float uPulse, uTime; varying vec3 vN; varying vec3 vV; varying vec3 vP;
    void main(){
      vec3 p = position; float down = smoothstep(1.0,-0.2,p.y); float a = atan(p.z,p.x);
      p.xz *= 1.0 - 0.16*uPulse*down; p.y *= 1.0 + 0.10*uPulse;
      p.y += 0.05*sin(a*14.0+uTime*2.0)*smoothstep(0.25,-0.2,p.y);
      vP = position; vec4 mv = modelViewMatrix*vec4(p,1.0);
      vV = normalize(-mv.xyz); vN = normalize(normalMatrix*normal);
      gl_Position = projectionMatrix*mv;
    }`;
  const bellMat = new THREE.ShaderMaterial({ uniforms:U, transparent:true, depthWrite:false, side:THREE.DoubleSide, vertexShader:vert,
    fragmentShader:`
      uniform float uTime; varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main(){
        float fr = pow(1.0-abs(dot(normalize(vN),normalize(vV))),2.2);
        float a = atan(vP.z,vP.x); float rib = smoothstep(0.9,1.0,cos(a*18.0));
        float down = smoothstep(1.0,-0.2,vP.y);
        vec3 col = mix(vec3(0.33,0.55,0.90), vec3(0.10,0.22,0.48), down*0.7);
        col = mix(col, vec3(0.93,0.88,0.80), (1.0-down)*0.35*(1.0-fr));
        col = mix(col, vec3(0.08,0.18,0.38), rib*0.5);
        col += fr*vec3(0.30,0.40,0.55);
        gl_FragColor = vec4(col, clamp(0.55+0.35*fr+rib*0.2,0.0,0.9));
      }`});
  const bellGeo = new THREE.SphereGeometry(1,96,48,0,Math.PI*2,0,Math.PI*0.54); bellGeo.scale(1.08,0.66,1.08);
  const bell = new THREE.Mesh(bellGeo, bellMat); bell.renderOrder = 5; jelly.add(bell);
  const innerGeo = new THREE.SphereGeometry(0.62,48,24,0,Math.PI*2,0,Math.PI*0.5); innerGeo.scale(1,0.7,1);
  const inner = new THREE.Mesh(innerGeo, new THREE.ShaderMaterial({ uniforms:U, transparent:true, depthWrite:false, side:THREE.DoubleSide, vertexShader:vert,
    fragmentShader:`varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main(){ float fr=pow(1.0-abs(dot(normalize(vN),normalize(vV))),1.5); float a=atan(vP.z,vP.x);
        float l=smoothstep(0.3,1.0,cos(a*4.0))*smoothstep(0.1,0.7,vP.y);
        vec3 c=mix(vec3(0.95,0.90,0.82),vec3(0.62,0.74,0.90),fr); c=mix(c,vec3(0.86,0.76,0.62),l*0.6);
        gl_FragColor=vec4(c,0.18+l*0.35+fr*0.15);}`}));
  inner.position.y = -0.05; inner.renderOrder = 4; jelly.add(inner);

  const ribbonMat = (c1,c2,op) => new THREE.ShaderMaterial({ transparent:true, depthWrite:false, side:THREE.DoubleSide,
    uniforms:{c1:{value:new THREE.Color(c1)}, c2:{value:new THREE.Color(c2)}, op:{value:op}},
    vertexShader:`varying vec2 vUv; void main(){vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader:`uniform vec3 c1,c2; uniform float op; varying vec2 vUv;
      void main(){ float e=1.0-pow(abs(vUv.x-0.5)*2.0,2.0); gl_FragColor=vec4(mix(c1,c2,vUv.y), op*e*(1.0-smoothstep(0.55,1.0,vUv.y))); }`});
  function ribbon(n, mat, order){
    const g = new THREE.BufferGeometry(), pos = new Float32Array(n*6), uv = new Float32Array(n*4), idx = [];
    for(let i=0;i<n;i++){ uv.set([0,i/(n-1),1,i/(n-1)], i*4); if(i<n-1){const a=i*2; idx.push(a,a+1,a+2,a+1,a+3,a+2);} }
    g.setAttribute('position', new THREE.BufferAttribute(pos,3)); g.setAttribute('uv', new THREE.BufferAttribute(uv,2)); g.setIndex(idx);
    const m = new THREE.Mesh(g, mat); m.frustumCulled = false; m.renderOrder = order; jelly.add(m);
    return {g, pos, n};
  }
  function setRibbon(r, pts, wf){
    for(let i=0;i<r.n;i++){ const [x,y,z]=pts[i], w=wf(i/(r.n-1))*0.5; r.pos.set([x-w,y,z,x+w,y,z], i*6); }
    r.g.attributes.position.needsUpdate = true;
  }
  const tm = ribbonMat('#3F6FB3','#AFC2D8',0.9), am = ribbonMat('#6E98D6','#E8DCC6',0.75);
  const T = Array.from({length:26}, (_,i)=>({r:ribbon(60,tm,2), ang:i/26*Math.PI*2, len:2.6+Math.random()*2.2, ph:Math.random()*6.28, w:0.03+Math.random()*0.03}));
  const A = Array.from({length:5}, (_,i)=>({r:ribbon(50,am,3), ang:i/5*Math.PI*2, len:2+Math.random()*1.5, ph:Math.random()*6.28, w:0.24+Math.random()*0.1}));

  const NP = 160, pg = new THREE.BufferGeometry(), pp = new Float32Array(NP*3);
  for(let i=0;i<NP;i++){ pp[i*3]=(Math.random()-.5)*18; pp[i*3+1]=(Math.random()-.5)*10; pp[i*3+2]=(Math.random()-.5)*6; }
  pg.setAttribute('position', new THREE.BufferAttribute(pp,3));
  scene.add(new THREE.Points(pg, new THREE.PointsMaterial({color:0x6E7F94, size:0.035, transparent:true, opacity:0.4, depthWrite:false})));

  let mx=0, my=0, smx=0, smy=0, homeX = 3, homeY = 0.9;
  addEventListener('pointermove', e => { mx = e.clientX/innerWidth*2-1; my = -(e.clientY/innerHeight*2-1); });
  function resize(){
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
    const viewW = 2*10*Math.tan(THREE.MathUtils.degToRad(17.5))*camera.aspect;
    const narrow = innerWidth < 760;
    homeX = narrow ? viewW*0.22 : viewW*0.33; homeY = narrow ? 1.9 : 0.9;
    jelly.scale.setScalar(narrow ? 0.62 : Math.min(1, viewW/12));
  }
  addEventListener('resize', resize); resize();

  // the app can nudge the jellyfish mood: 'calm' | 'alert' | 'danger'
  let mood = 'calm', moodK = 0;
  window.RedflagJelly = { setMood(m){ mood = m; } };

  const clock = new THREE.Clock(); let pts = [];
  function frame(){
    const dt = Math.min(0.05, clock.getDelta()), t = clock.elapsedTime * (reduce ? 0.3 : 1);
    moodK += ((mood==='danger'?1:mood==='alert'?0.5:0) - moodK)*0.03;
    const speed = 0.55 + moodK*0.5;
    const cyc = (t*speed) % 1, pulse = cyc < 0.3 ? Math.sin(cyc/0.3*Math.PI/2) : Math.cos((cyc-0.3)/0.7*Math.PI/2);
    U.uPulse.value = pulse; U.uTime.value = t;
    smx += (mx-smx)*0.015; smy += (my-smy)*0.015;
    jelly.position.set(homeX + smx*0.5 + Math.sin(t*0.3)*0.3, homeY + smy*0.25 + Math.sin(t*0.5)*0.2 + pulse*0.12, 0);
    jelly.rotation.set(0.16 + smy*0.1, t*0.1, -smx*0.12 + Math.sin(t*0.6)*0.06);
    const rim = 1.04*(1-0.16*pulse), ry = -0.1;
    T.forEach(c => { pts.length = 0; const ca=Math.cos(c.ang), sa=Math.sin(c.ang);
      for(let i=0;i<60;i++){ const s=i/59;
        pts.push([ca*rim*0.96*(1+s*0.25) + Math.sin(t*1.4-s*5+c.ph)*0.3*s + Math.sin(t*2.1-s*13+c.ph)*0.07*s,
                  ry - s*c.len + pulse*0.18*s, sa*rim*0.96*(1+s*0.25) + Math.sin(t*0.9-s*9+c.ph*2)*0.12*s]); }
      setRibbon(c.r, pts, s => c.w*(1-s*0.8)); });
    A.forEach(a => { pts.length = 0; const ca=Math.cos(a.ang+t*0.1), sa=Math.sin(a.ang+t*0.1);
      for(let i=0;i<50;i++){ const s=i/49, tw=Math.sin(t*0.8+s*3+a.ph)*0.12;
        pts.push([ca*(0.16+tw*s) + Math.sin(t*1.1-s*4+a.ph)*0.28*s, -0.1 - s*a.len + pulse*0.12*s, sa*(0.16+tw*s)]); }
      setRibbon(a.r, pts, s => a.w*(1-s*0.75)*(0.7+0.3*Math.sin(s*34-t*3+a.ph))); });
    const P = pg.attributes.position.array;
    for(let i=0;i<NP;i++){ P[i*3+1] += 0.003 + (i%7)*0.0004; if(P[i*3+1] > 5) P[i*3+1] = -5; }
    pg.attributes.position.needsUpdate = true;
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  frame();
})();
