/* GitHub Pages: UI-only preview. No devices, inference, or live measurements. */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const unavailable = 'UI preview only — hardware controls, AI inference and calibration require the local PC application.';
  const profile = {name:'UI preview (no calibration)',usable:false,problems:['No device connected']};
  const imu = {
    session:'static-ui-preview',mode:'idle',status:'disconnected',port:'',label:'',error:'',
    stale:true,paused:false,sample_age_s:null,samples:0,latest:null,history:[],
    diagnostics:[],stats:{},sample_hz:null,profile,
    replay:{elapsed_s:0,duration_s:0}
  };
  const state = {
    service_id:'github-pages-ui-preview',camera_port:'',
    pose:{phase:'未开始',reps:0,action:'深蹲',angles:{},last:null},
    stats:{state:'Vision disabled',frames:0,fps:0,alarm:false,radio:{ack:0},
      vision_alive:false,frame_age_s:null,video_language:'en'},
    imu,
    modules:{
      camera:{enabled:false,connected:false,status:'disabled'},
      imu:{enabled:false,connected:false,status:'disabled'},
      arduino:{enabled:false,connected:false,status:'disabled'}
    },
    training:{status:'idle',elapsed_s:0,exercise:'squat'}
  };
  function json(data,status=200) {
    return Promise.resolve(new Response(JSON.stringify(data),{
      status,headers:{'Content-Type':'application/json; charset=utf-8'}
    }));
  }
  window.fetch = (input, options) => {
    const value = typeof input === 'string' ? input : input.url;
    const path = new URL(value, location.href).pathname;
    if(path.endsWith('/api/state')) return json(state);
    if(path.endsWith('/api/ports')) return json({ports:[],camera_port:''});
    if(path.endsWith('/api/profile') && (!options || !options.method || options.method==='GET')) return json(profile);
    if(path.includes('/api/') || path.endsWith('/stats')) return json({error:unavailable},403);
    if(value==='/locales.json' || value==='/exercises.json') return nativeFetch('.'+value,options);
    return nativeFetch(input,options);
  };
  window.addEventListener('DOMContentLoaded',()=>{
    const notice=document.createElement('div');
    notice.setAttribute('role','status');
    notice.style.cssText='position:sticky;top:0;z-index:9999;padding:10px 18px;background:#f9eedb;color:#654a35;text-align:center;font:600 13px/1.5 system-ui;border-bottom:1px solid #eb9861';
    notice.textContent='FITCOACH AI · UI-ONLY PREVIEW — No camera, IMU, Arduino, AI inference or live data. The complete application runs locally.';
    document.body.prepend(notice);
    const tag=document.querySelector('.workspace-tag');
    if(tag)tag.textContent='INT4089 · UI preview';
    const header=document.querySelector('.header-right .tag');
    if(header)header.textContent='UI DEMO';
    const live=document.querySelector('.header-right .live-dot');
    if(live)live.style.background='#b0aaa2';
    const avatar=document.querySelector('.avatar');
    if(avatar){avatar.textContent='FC';avatar.removeAttribute('aria-label');}
    document.querySelectorAll('#enableCamera,#enableImu,#enableArduino,#connect,#disconnect,#reconnectVision,#example,#uploadCsv,#calibrate,#applyProfile,#startSession,#startExercise,#startSession,#pauseSession,#stopSession,#refreshPorts,#resetFilter,#origin,#recalibrateOrientation').forEach(el=>{
      el.disabled=true;
      el.title=unavailable;
    });
    const image=document.querySelector('.video-wrap img');
    if(image){image.removeAttribute('src');image.alt='No live video in UI-only preview';}
  });
})();
