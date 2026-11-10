"""Independent host-side module switches and a training session lifecycle."""
import threading
import time

class Workspace:
    def __init__(self,server,camera=True,imu=True,imu_port='COM4'):
        self.server=server
        self.lock=threading.RLock()
        self.enabled={'camera':camera,'imu':imu,'arduino':True}
        self.imu_port=imu_port
        self.session='idle'
        self.elapsed=0.0
        self.since=None

    def configure_pipeline(self,pipeline):
        pipeline.alarm_enabled=self.enabled['arduino']
        active=self.session=='running'
        if pipeline.training_active!=active:pipeline.requested_partial_reset+=1
        pipeline.training_active=active
        pipeline.training_status=self.session

    def _silence(self):
        with self.server.vision_module._LOCK:self.server.vision_module.STATE['stats']['alarm']=False
        pipeline=self.server.pipeline
        if pipeline:
            source=getattr(pipeline,'_source',None)
            if source and hasattr(source,'set_alarm'):source.set_alarm(False)

    def camera(self,enabled,reconnect=False):
        with self.lock,self.server.vision_control:
            old=self.server.pipeline
            if old and old.is_alive():
                if enabled and not reconnect and old.running:return
                old.training_active=False
                old.running=False
                self._silence()
                old.join(timeout=5)
                if old.is_alive():raise ValueError('Camera is still stopping; retry shortly')
            self.enabled['camera']=enabled
            if not enabled:
                self.training('pause',allow_idle=True)
                with self.server.vision_module._LOCK:
                    self.server.vision_module.STATE.update(jpeg=None)
                    self.server.vision_module.STATE['stats'].update(state='Vision disabled',alarm=False,persons=0,fps=0)
                return
            vision=self.server.vision_module
            pipeline=vision.Pipeline(self.server.vision_source,self.server.vision_action,
                self.server.vision_rotate,engine=getattr(old,'engine',None),mirror=self.server.vision_mirror)
            pipeline.requested_orientation=(self.server.vision_rotate,self.server.vision_mirror,self.server.orientation_revision)
            pipeline.language=self.server.vision_language
            self.configure_pipeline(pipeline)
            with vision._LOCK:
                vision.STATE.update(jpeg=None)
                vision.STATE['stats'].update(alarm=False,state='Connecting',fps=0,persons=0)
            self.server.pipeline=pipeline
            pipeline.start()

    def module(self,name,enabled,port=None):
        if name not in self.enabled or not isinstance(enabled,bool):raise ValueError('Invalid module settings')
        with self.lock:
            if name=='camera':self.camera(enabled)
            elif name=='imu':
                if enabled:
                    self.server.imu.connect(port or self.imu_port,reset=False)
                    self.imu_port=port or self.imu_port
                else:self.server.imu.disconnect()
                self.enabled[name]=enabled
            else:
                self.enabled[name]=enabled
                if self.server.pipeline:self.server.pipeline.alarm_enabled=enabled
                if not enabled:self._silence()

    def training(self,action,exercise='squat',allow_idle=False):
        if action not in ('start','pause','resume','stop'):raise ValueError('Invalid training action')
        with self.lock:
            pipeline=self.server.pipeline
            if action in ('start','resume'):
                if exercise!='squat':raise ValueError('Exercise AI is not available yet')
                if not self.enabled['camera']:raise ValueError('Enable ESP Camera before starting training')
                if not pipeline or not pipeline.is_alive() or not pipeline.last_frame_at or time.monotonic()-pipeline.last_frame_at>=2:
                    raise ValueError('Camera is not ready for training')
                if action=='resume' and self.session!='paused':raise ValueError('No paused training session')
                if action=='start':
                    self.elapsed=0.0
                    pipeline.requested_reset+=1
                    pipeline.requested_action=exercise
                self.since=time.monotonic()
                self.session='running'
            else:
                if self.session=='running' and self.since is not None:self.elapsed+=time.monotonic()-self.since
                self.since=None
                if action=='pause':
                    if self.session not in ('running','paused'):
                        if allow_idle:return
                        raise ValueError('No active training session')
                    self.session='paused'
                else:self.session='ended'
                self._silence()
            if pipeline:self.configure_pipeline(pipeline)

    def snapshot(self,stats,imu):
        with self.lock:
            live=bool(stats.get('vision_alive') and stats.get('frame_age_s') is not None and stats['frame_age_s']<2 and stats.get('state')=='运行中')
            radio=stats.get('radio') or {}
            try:relay=live and int(radio.get('ack',0))>0 and int(radio.get('ack_age_ms',999999))<1200
            except (ValueError,TypeError):relay=False
            imu_connected=imu['mode']=='live' and not imu['stale'] and bool(imu['samples'])
            elapsed=self.elapsed+(time.monotonic()-self.since if self.since is not None else 0)
            return {'modules':{
                'camera':{'enabled':self.enabled['camera'],'connected':live,'status':'online' if live else 'waiting' if self.enabled['camera'] else 'disabled'},
                'imu':{'enabled':self.enabled['imu'],'connected':imu_connected,'status':'online' if imu_connected else 'fault' if imu['error'] else 'waiting' if self.enabled['imu'] else 'disabled'},
                # One-way Mega UART has no actuator acknowledgement. Never call this confirmed hardware connectivity.
                'arduino':{'enabled':self.enabled['arduino'],'connected':False,'relay_ready':relay,'status':'relay_ready' if relay else 'unconfirmed' if self.enabled['arduino'] else 'disabled'}},
                'training':{'status':self.session,'elapsed_s':round(elapsed,1),'exercise':self.server.vision_action}}
