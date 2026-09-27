"""Offline listening render. Same gain for A/B/null, no implicit individual normalisation."""
from __future__ import annotations
import math
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy import signal
from .dsp import Model, sos_array


def test_signal(fs):
    rng=np.random.default_rng(713)
    n=fs*4; t=np.arange(n)/fs
    y=.06*rng.normal(size=n)
    y=signal.sosfilt(signal.butter(2,min(6000,fs*.4),fs=fs,output='sos'),y)
    y+=.07*np.sin(2*np.pi*110*t)+.03*np.sin(2*np.pi*997*t)
    y*=.5+.5*np.sin(2*np.pi*.9*t)**2
    fade=min(fs//20,n//2)
    y[:fade]*=np.linspace(0,1,fade); y[-fade:]*=np.linspace(1,0,fade)
    return y


def render_ab(target,model:Model,path=None,match_rms=False):
    fs=model.fs
    if path:
        a,src=sf.read(path,dtype='float64',always_2d=True,frames=sf.info(path).samplerate*30)
        if a.shape[1]>2: a=a[:,:2]
        if src!=fs:
            g=math.gcd(src,fs)
            a=signal.resample_poly(a,fs//g,src//g,axis=0,window=('kaiser',8.6))
    else:
        a=test_signal(fs)[:,None]
    if not np.all(np.isfinite(a)): raise ValueError('Audio contains NaN/Inf.')
    max_len=len(a)+min(len(target),fs*8)-1
    reference=[]; model_out=[]
    s=sos_array(model.sections,fs)
    for ch in range(a.shape[1]):
        y=signal.fftconvolve(a[:,ch],target)[:max_len]
        z=signal.fftconvolve(a[:,ch],model.fir) if model.fir_enabled else a[:,ch].copy()
        z=np.pad(z,(0,max(0,len(y)-len(z))))[:len(y)]
        if len(s): z=signal.sosfilt(s.copy(),z)
        reference.append(y); model_out.append(z)
    A=np.asarray(reference).T; B=np.asarray(model_out).T
    gain_match=1.
    if match_rms:
        gain_match=float(np.sqrt(np.mean(A*A)/max(np.mean(B*B),1e-30)))
        B*=gain_match
    D=B-A
    common=.5/max(np.max(abs(A)),np.max(abs(B)),np.max(abs(D)),.5)
    return {'A':A*common,'B':B*common,'D':D*common},fs,{'shared_monitor_gain':common,'model_rms_match_gain':gain_match}


class Player:
    def __init__(self):
        self.process=None
        self.folder=Path(tempfile.mkdtemp(prefix='irbq_listen_'))
    def stop(self):
        if platform.system()=='Windows':
            import winsound
            winsound.PlaySound(None,0)
        if self.process is not None:
            self.process.terminate(); self.process=None
    def play(self,data,fs):
        self.stop()
        path=self.folder/'preview.wav'
        sf.write(path,np.clip(data,-1,1),fs,subtype='PCM_16')
        if platform.system()=='Windows':
            import winsound
            winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_ASYNC)
        elif shutil.which('afplay'):
            self.process=subprocess.Popen(['afplay',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        elif shutil.which('aplay'):
            self.process=subprocess.Popen(['aplay','-q',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        elif shutil.which('paplay'):
            self.process=subprocess.Popen(['paplay',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        elif shutil.which('ffplay'):
            self.process=subprocess.Popen(['ffplay','-nodisp','-autoexit','-loglevel','quiet',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            raise RuntimeError('Нет системного WAV-плеера. Экспортируйте A/B WAV и слушайте в DAW.')
    def close(self):
        self.stop()
        shutil.rmtree(self.folder,ignore_errors=True)
