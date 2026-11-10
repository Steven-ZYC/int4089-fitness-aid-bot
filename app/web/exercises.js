/* Technique previews are independent from the active AI exercise. */
'use strict';
window.FitCoachExercises=(()=>{
let exercises=[],selected='squat',controls=null,playing=false;
const tr=value=>window.FitCoachI18n.t(value);
function el(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text)node.textContent=tr(text);return node;}
const current=()=>exercises.find(e=>e.id===selected);
function stopVideo(){if(playing){playing=false;renderVideo();}}
function renderVideo(){
const item=current(),host=document.getElementById('guideVideo');if(!item||!host)return;
host.replaceChildren();
if(playing){
 const frame=document.createElement('iframe');
 const language=window.FitCoachI18n.locale==='en'?'en':window.FitCoachI18n.locale==='zh-HK'?'zh-HK':'zh-CN';
 frame.src=`https://www.youtube-nocookie.com/embed/${item.video.id}?autoplay=1&rel=0&hl=${language}&origin=${encodeURIComponent(location.origin)}`;
 frame.title=tr('视频播放区域')+' · '+tr(item.name);frame.referrerPolicy='strict-origin-when-cross-origin';
 frame.allow='accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; web-share';frame.allowFullscreen=true;
 const close=el('button','close-tutorial','关闭视频');close.addEventListener('click',stopVideo);host.append(frame,close);return;
}
const button=el('button','tutorial-poster');button.setAttribute('aria-label',tr('点击播放示范视频')+' · '+tr(item.name));
const image=el('img');image.src=item.video.poster;image.alt=item.video.title;image.loading='lazy';image.referrerPolicy='no-referrer';
image.addEventListener('error',()=>{image.hidden=true;});
button.append(image,el('span','poster-shade'),el('span','play-symbol','▶'));
const caption=el('span','poster-caption');caption.append(el('small','',item.video.author),el('strong','',item.video.title),el('span','','点击播放示范视频'));
button.append(caption);button.addEventListener('click',()=>{playing=true;renderVideo();});host.append(button);
}
function renderCards(){
for(const container of document.querySelectorAll('[data-exercise-options]')){
 container.replaceChildren();
 for(const item of exercises){
 const button=el('button','exercise-option'+(item.id===selected?' selected':''));button.dataset.exercise=item.id;button.setAttribute('aria-pressed',String(item.id===selected));
 const image=el('img','exercise-thumb');image.src=item.video.poster;image.alt='';image.loading='lazy';image.referrerPolicy='no-referrer';image.addEventListener('error',()=>image.hidden=true);
 const copy=el('span','exercise-copy');copy.append(el('strong','',item.name),el('small','',item.group));
 const status=el('span','exercise-availability'+(item.available?' available':''),item.available?'AI 已开放':'AI 即将开放');
 button.append(image,copy,status,el('span','exercise-arrow','↗'));
 button.addEventListener('click',()=>{selected=item.id;playing=false;render();controls.showView('exercises');});container.append(button);
 }
}
}
const poses={
 squat:[{head:[86,27],shoulder:[86,52],hip:[85,105],knee:[85,145],foot:[85,179],elbow:[110,77],hand:[115,107]},
 {head:[119,57],shoulder:[111,81],hip:[73,119],knee:[119,136],foot:[106,179],elbow:[143,84],hand:[164,87]},
 {head:[86,27],shoulder:[86,52],hip:[85,105],knee:[85,145],foot:[85,179],elbow:[110,77],hand:[115,107]}],
 pushup:[{head:[26,81],shoulder:[54,89],hip:[108,101],knee:[145,111],foot:[177,121],elbow:[57,128],hand:[60,173]},
 {head:[23,124],shoulder:[53,132],hip:[108,142],knee:[145,150],foot:[177,155],elbow:[82,154],hand:[60,173]},
 {head:[26,81],shoulder:[54,89],hip:[108,101],knee:[145,111],foot:[177,121],elbow:[57,128],hand:[60,173]}],
 lunge:[{head:[90,27],shoulder:[90,52],hip:[90,105],knee:[90,145],foot:[90,179],elbow:[110,78],hand:[105,105]},
 {head:[104,35],shoulder:[104,60],hip:[104,105],knee:[151,121],foot:[151,179],elbow:[124,79],hand:[121,107],backKnee:[63,164],backFoot:[35,179]},
 {head:[90,27],shoulder:[90,52],hip:[90,105],knee:[90,145],foot:[90,179],elbow:[110,78],hand:[105,105]}]
};
function drawDiagram(item){
const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 720 228');svg.setAttribute('role','img');svg.setAttribute('aria-label',tr('动作示意')+' · '+tr(item.name));
function add(tag,attrs,parent=svg,text){const node=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attrs))node.setAttribute(key,String(value));if(text)node.textContent=text;parent.append(node);return node;}
poses[item.id].forEach((p,index)=>{
 const group=add('g',{transform:`translate(${index*240+10},0)`});
 add('rect',{x:0,y:0,width:220,height:225,rx:12,fill:index===1?'#f9eedb':'#f1f5f7'},group);
 add('line',{x1:20,y1:183,x2:199,y2:183,stroke:'#cbd8dd','stroke-dasharray':'3 5'},group);
 function limb(points,color='#eb9861',width=7){add('polyline',{points:points.map(v=>v.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':width,'stroke-linecap':'round','stroke-linejoin':'round'},group);}
 if(p.backKnee)limb([p.hip,p.backKnee,p.backFoot],'#bdd6e8');
 else limb([p.hip,[p.knee[0]-12,p.knee[1]+2],[p.foot[0]-13,p.foot[1]]],'#bdd6e8',6);
 limb([p.shoulder,p.hip,p.knee,p.foot]);limb([p.shoulder,p.elbow,p.hand],'#687c88',5);
 limb([[p.foot[0]-3,p.foot[1]],[p.foot[0]+15,p.foot[1]]],'#687c88',5);
 limb([p.head,p.shoulder],'#687c88',5);add('circle',{cx:p.head[0],cy:p.head[1],r:12,fill:'#fbfcfc',stroke:'#687c88','stroke-width':4},group);
 if(index===1){const marks=item.id==='pushup'?[p.hand,p.hip,p.shoulder]:[p.shoulder,p.hip,p.knee];marks.forEach(([x,y],n)=>{add('circle',{cx:x-12,cy:y-12,r:8,fill:'#fbfcfc',stroke:'#c58a5f'},group);add('text',{x:x-12,y:y-9,'text-anchor':'middle','font-size':9,fill:'#9c673f'},group,String(n+1));});}
 add('text',{x:110,y:210,'text-anchor':'middle','font-size':11,fill:'#71818a'},group,tr(item.stages[index]));
});
document.getElementById('guideDiagram').replaceChildren(el('h3','','动作示意'),svg);
}
function render(){
const item=current();if(!item)return;
renderCards();document.getElementById('guideTitle').textContent=tr(item.name)+' · '+tr('动作示范');
const status=document.getElementById('guideAvailability');status.textContent=tr(item.available?'AI 已开放':'AI 即将开放');status.className='pill '+(item.available?'good':'');
document.getElementById('guideAuthor').textContent=item.video.author+' · YouTube';
document.getElementById('guideWatch').href=item.video.watch_url;
document.getElementById('guideSource').href=item.source;
const list=document.getElementById('guideCues');list.replaceChildren();
item.cues.forEach(([title,body],index)=>{const row=el('li');row.append(el('span','cue-number',String(index+1).padStart(2,'0')));const text=el('div');text.append(el('h3','',title),el('p','',body));row.append(text);list.append(row);});
const notice=document.getElementById('guidePreviewNotice');notice.textContent=item.available?'':tr('此动作暂未开放 AI 识别，可先观看示范和学习要点。');notice.hidden=item.available;
const start=document.getElementById('startExercise');start.disabled=!item.available;start.textContent=tr(item.available?'开始深蹲训练':'AI 即将开放');
renderVideo();drawDiagram(item);
}
async function init(options){
 controls=options;const response=await fetch('/exercises.json');if(!response.ok)throw Error('Unable to load exercise library');exercises=await response.json();
 document.getElementById('startExercise').addEventListener('click',async()=>{const item=current();if(!item?.available)return;try{await controls.request('/api/vision/action',{action:item.id});controls.showView('overview');}catch(_) {}});render();
}
return{init,render,stopVideo};
})();
