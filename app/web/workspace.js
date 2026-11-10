/* Dashboard module switches reflect host intent and measured device state separately. */
'use strict';
window.FitCoachWorkspace=(()=>{
let controls=null,last=null,busy=new Set(),activeExercise='squat',preview=null;
const ids={camera:'enableCamera',imu:'enableImu',arduino:'enableArduino'};
const tr=v=>window.FitCoachI18n.t(v),by=id=>document.getElementById(id);
function status(value){return tr({online:'已连接',waiting:'等待设备',fault:'设备异常',disabled:'已停用',unconfirmed:'未确认',relay_ready:'中继就绪'}[value]||'等待设备');}
function update(data){
 last=data;const modules=data.modules||{},training=data.training||{status:'idle',elapsed_s:0,exercise:'squat'},state=training.status;
 activeExercise=training.exercise;const previewOnly=preview&&!preview.available&&state!=='running'&&state!=='paused';
 by('trainingName').textContent=tr(previewOnly?preview.name:'深蹲');
 for(const [name,id]of Object.entries(ids)){
  const module=modules[name]||{enabled:false,status:'waiting'};
  if(!busy.has(name))by(id).checked=module.enabled;
  by(id).disabled=busy.has(name);
  const label=by(name==='camera'?'cameraStatus':name==='imu'?'imuHardwareStatus':'arduinoStatus');
  label.textContent=status(module.status);label.className='module-connection '+(module.connected?'connected':module.status==='disabled'?'disabled':'pending');
  by(id).closest('.hardware-module').classList.toggle('module-disabled',!module.enabled);
 }
 const camera=modules.camera||{};
 const empty=by('visionEmpty');if(empty.firstChild)empty.firstChild.textContent=tr(camera.enabled?'等待摄像头图像':'ESP Camera 已停用');
 const helper=empty.querySelector('small');if(helper)helper.textContent=tr(camera.enabled?'检查 USB 连接后，点击「重连摄像头」。':'启用 ESP Camera 后可查看实时画面。');
 if(!camera.enabled)by('visionState').textContent=tr('ESP Camera 已停用');
 by('reconnectVision').disabled=!camera.enabled;
 const live=camera.connected;
 by('monitorBadge').textContent=tr(state==='running'?(live?'实时监测中':'等待设备'):state==='paused'?'训练暂停':state==='ended'?'训练结束':'训练未开始');
 by('monitorBadge').className='pill '+(state==='running'&&live?'good':'');
 by('activeAiState').textContent=tr(state==='running'&&live?'AI 已开启':state==='paused'?'AI 已暂停':'AI 已开放');
 by('activeAiState').className='pill '+(state==='running'&&live?'good':'');
 const seconds=Math.floor(training.elapsed_s||0);by('sessionTime').textContent=[Math.floor(seconds/60),seconds%60].map(n=>String(n).padStart(2,'0')).join(':');
 by('startSession').hidden=state==='running'||state==='paused';by('startSession').textContent=tr(state==='ended'?'再次训练':'开始训练');
 by('pauseSession').hidden=state!=='running'&&state!=='paused';by('pauseSession').textContent=tr(state==='paused'?'继续训练':'暂停训练');
 by('startSession').disabled=!camera.enabled;
 if(state!=='running')by('phase').textContent=tr(state==='paused'?'已暂停':state==='ended'?'训练结束':'训练未开始');
 by('stopSession').disabled=state!=='running'&&state!=='paused';
 const result=data.pose?.last;by('formState').textContent=tr(state==='running'&&!live?'等待设备':state==='paused'?'已暂停':state!=='running'?'等待训练':result?(result.ok?'姿势良好':'需要调整'):'等待动作');
 by('formState').closest('.form-metric').classList.toggle('good',state==='running'&&live&&!!result?.ok);
 if(state!=='running')by('verdict').textContent=tr(state==='paused'?'训练已暂停，计次与报警已停止。':state==='ended'?'训练已结束，可选择动作开始下一次训练。':'请先选择动作并开始训练。');
 if(previewOnly){by('activeAiState').textContent=tr('AI 即将开放');by('startSession').disabled=true;by('startSession').textContent=tr('AI 即将开放');by('reps').textContent='—';by('verdict').textContent=tr('此动作暂未开放 AI 识别，可先观看示范和学习要点。');}
 by('overviewCameraStatus').textContent=status(camera.status);
 by('overviewImuStatus').textContent=data.imu.mode==='replay'?tr('CSV 回放'):status(modules.imu?.status);
 by('overviewProfileStatus').textContent=tr(data.imu.profile.usable?'校准门槛通过':'校准待检查');
 by('motionInsightCaption').textContent=tr(data.imu.mode==='replay'?'历史 CSV · 非实时':data.imu.latest&&data.imu.stale?'数据已过期':'基于 IMU 的实时姿态。');
 by('positionSummary').textContent=data.imu.latest&&data.imu.stale?tr('数据已过期'):data.imu.latest?(data.imu.mode==='replay'?tr('历史 CSV · 非实时'):tr('实时')):tr('等待 IMU 数据');
}
async function start(exercise='squat'){preview=null;await controls.request('/api/training',{action:'start',exercise});controls.showView('realtime');}
function init(options){
 controls=options;
 for(const [name,id]of Object.entries(ids))by(id).addEventListener('change',async event=>{
  const enabled=event.target.checked;busy.add(name);event.target.disabled=true;
  try{await controls.request('/api/modules',{module:name,enabled,port:by('imuPort').value||'COM4'});}
  catch(_){event.target.checked=!enabled;}
  finally{busy.delete(name);event.target.disabled=false;}
 });
 const action=(id,fn)=>by(id).addEventListener('click',async()=>{by(id).disabled=true;try{await fn();}catch(_){}finally{by(id).disabled=false;}});
 action('startSession',()=>start(activeExercise));action('pauseSession',()=>controls.request('/api/training',{action:last?.training.status==='paused'?'resume':'pause',exercise:activeExercise}));action('stopSession',()=>controls.request('/api/training',{action:'stop'}));
 action('fullscreenVideo',()=>by('liveVideo').closest('.video-wrap').requestFullscreen());
}
return{init,update,start,selectExercise(item){preview=item;if(last)update(last);},get exercise(){return activeExercise;}};
})();
