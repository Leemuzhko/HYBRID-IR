"""Headless interface using the exact same engine as the GUI."""
import argparse
from pathlib import Path
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ.setdefault(k,'1')
import numpy as np
from .project import Session,export_model
from .dsp import PrepConfig,Model,preset_sections
from .trainer import TrainConfig,train

def main():
    p=argparse.ArgumentParser(description='IRBQ Lab independent FIR+BQ trainer')
    p.add_argument('wav');p.add_argument('--out',default='export');p.add_argument('--fs',type=int,default=44100)
    p.add_argument('--taps',type=int,default=128);p.add_argument('--bq',type=int,default=8)
    p.add_argument('--mode',choices=['pairs','joint','bq','fir'],default='pairs')
    p.add_argument('--fir-bypass',action='store_true',help='Disable FIR in the signal path; stored taps are preserved. Useful with --mode bq.')
    p.add_argument('--lowcut',action='store_true');p.add_argument('--iterations',type=int,default=100)
    p.add_argument('--rounds',type=int,default=2);p.add_argument('--restarts',type=int,default=1)
    p.add_argument('--no-mpt',action='store_true');p.add_argument('--no-seed',action='store_true')
    args=p.parse_args()
    s=Session(config=PrepConfig(fs=args.fs,minimum_phase=not args.no_mpt));s.load_audio(args.wav);s.preprocess()
    s.model=Model(args.fs,np.pad(s.target[:args.taps],(0,max(0,args.taps-len(s.target)))),
                  preset_sections(args.bq,args.lowcut,args.fs),f'{args.taps}+{args.bq}',fir_enabled=not args.fir_bypass)
    cfg=TrainConfig(mode=args.mode,iterations=args.iterations,rounds=args.rounds,restarts=args.restarts,initialize=not args.no_seed)
    s.model=train(s.target,s.model,cfg,progress=lambda x,t:print(f'{x:3.0f}% {t}',flush=True))
    folder=Path(args.out);export_model(folder,s);s.save(folder/'project.irbq')
    print('Saved:',folder.resolve())

if __name__=='__main__':main()
