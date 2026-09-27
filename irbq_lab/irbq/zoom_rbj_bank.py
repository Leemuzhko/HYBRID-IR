"""HVB4: trained RBJ RESO, common RBJ PRES, exact correction SOS.

Only explicit RESO metadata owns a knob. Legacy names offer user-confirmed
migration, never automatic inference. No 61x5 coefficient tables in the bank.
"""
from dataclasses import replace
import math
import struct
import zlib

import numpy as np

from .dsp import Biquad, quantize_fir, sos_array
from .zoom_variable_bank import HEADER, MAX_BYTES, stable_denominator

MAGIC=int.from_bytes(b'HVB4','little')
GAIN_LUT=np.array(10**(np.linspace(-15,15,61)/40),dtype='<f4')
PRES_PARAMS=np.array([np.cos(2*np.pi*3500/44100),
                      np.sin(2*np.pi*3500/44100),1/.8-1],dtype='<f4')


def legacy_candidates(model):
    if any(b.control_role for b in model.sections):return {}
    found=[i for i,b in enumerate(model.sections) if b.name=='Resonance'
           and b.kind=='Peak' and b.enabled and b.raw is None]
    return {'reso':found[0]} if len(found)==1 else {}


def assign_roles(model,indices):
    """Explicit choice affects a clone only; all original coefficients remain."""
    if set(indices)!={'reso'}:raise ValueError('Choose one RESO filter')
    result=model.clone()
    if any(b.control_role not in ('','reso') for b in result.sections):
        raise ValueError('Unknown Zoom control role')
    for b in result.sections:b.control_role=''
    index=indices['reso']
    if type(index) is not int or not 0<=index<len(result.sections):
        raise ValueError('Invalid role section index')
    result.sections[index].control_role='reso'
    controls(result)
    return result


def controls(model):
    reso=None;correction=[]
    for b in model.sections:
        if b.control_role not in ('','reso'):raise ValueError('Unknown Zoom control role')
        if not b.control_role:correction.append(b);continue
        if reso is not None:raise ValueError('Duplicate Zoom control role: reso')
        if b.kind!='Peak' or b.raw is not None:
            raise ValueError('Zoom RESO requires an explicit parametric Peak')
        if not b.enabled:raise ValueError('Enable the RESO filter or clear its Zoom role')
        reso=b
    if len(correction)+2>32:raise ValueError('At most 32 BQ including RESO and common PRES')
    return (reso if reso is not None else Biquad(f=110.,q=.7,gain=0.),
            Biquad(kind='HighShelf',f=3500.,q=.8,gain=0.),correction)


def bq_count(model):return len(controls(model)[2])+2


def control_table(section):
    """Test reference only: tables are never stored in HVB4."""
    return np.array([replace(section,gain=section.gain+float(delta)).coefficients(44100)
                     [[0,1,2,4,5]] for delta in np.linspace(-15,15,61)],dtype='<f4')


def rbj_parameters(section):
    w=2*np.pi*section.f/44100
    return np.array([np.cos(w),np.sin(w)/(2*section.q),10**(section.gain/40)],dtype='<f4')


def rbj_coefficients(params,amplitude):
    """Float32 operation order of C; reciprocal is a host reference, not C674 parity."""
    cw,alpha,_=np.asarray(params,dtype='f4')
    a=np.float32(amplitude);v=np.float32(alpha*(np.float32(1)/a))
    r=np.float32(1)/np.float32(1+v);c1=np.float32(np.float32(-2)*cw*r)
    return np.array([np.float32(1+np.float32(alpha*a))*r,c1,
                     np.float32(1-np.float32(alpha*a))*r,c1,np.float32(1-v)*r],dtype='<f4')


def pres_coefficients(amplitude):
    a=np.float32(amplitude);cw,sw,term=PRES_PARAMS
    beta=np.float32(sw*np.sqrt(np.float32(np.float32(a*a+1)*term+np.float32(2*a))))
    ap=np.float32(a+1);am=np.float32(a-1);amcw=np.float32(am*cw);apcw=np.float32(ap*cw)
    r=np.float32(1)/np.float32(ap-amcw+beta)
    return np.array([np.float32(a*np.float32(ap+amcw+beta))*r,
                     np.float32(np.float32(-2*a)*np.float32(am+apcw))*r,
                     np.float32(a*np.float32(ap+amcw-beta))*r,
                     np.float32(2*np.float32(am-apcw))*r,np.float32(ap-amcw-beta)*r],dtype='<f4')


def validate_rbj(params):
    cw,alpha,nom=params
    if not all(map(math.isfinite,params)) or not -1<cw<1 or not 0<alpha<1e6 or not .01<nom<100:
        raise ValueError('Invalid RBJ RESO parameters')
    # Includes points between UI steps, vectorized for the bank UI. The C
    # core guards each actual ramp result, including intrinsic rounding.
    t=np.linspace(0,1,9,dtype='f4')[:,None]
    amplitudes=np.r_[np.ravel(GAIN_LUT[:-1]+t*(GAIN_LUT[1:]-GAIN_LUT[:-1])),GAIN_LUT[-1]]
    a=np.float32(nom)*amplitudes
    v=np.float32(alpha)*(np.float32(1)/a);r=np.float32(1)/(np.float32(1)+v)
    a1=(np.float32(-2)*np.float32(cw)*r).astype('f8')
    a2=((np.float32(1)-v)*r).astype('f8');margin=2**-20
    safe=(a2>-1+margin)&(a2<1-margin)&(np.abs(a1)<1+a2-margin)
    if not np.all(safe):raise ValueError('Insufficient-margin RBJ RESO denominator')


def pack(project):
    project.validate()
    fir_pool,bq_pool,desc=[],[],[];fir_seen,bq_seen={},{}
    for model in [None]+[s.model for s in project.slots]:
        if model is None:reso,pres,correction=Biquad(f=110.,q=.7),Biquad(kind='HighShelf',f=3500.,q=.8),[]
        else:reso,pres,correction=controls(model)
        params=rbj_parameters(reso)
        if model is not None and model.fir_enabled:
            q,scale=quantize_fir(model.fir);q=np.pad(q,(0,-len(q)%4));key=q.astype('<i2').tobytes()
            if key not in fir_seen:fir_seen[key]=len(fir_pool);fir_pool.extend(q.tolist())
            n,fi=len(q),fir_seen[key]
        else:n,fi,scale=0,0,1.
        rows=np.vstack((reso.coefficients(44100)[[0,1,2,4,5]],pres.coefficients(44100)[[0,1,2,4,5]],
                        sos_array(correction,44100,True)[:,[0,1,2,4,5]])).astype('<f4')
        key=rows.tobytes()
        if key not in bq_seen:bq_seen[key]=len(bq_pool);bq_pool.extend(rows.tolist())
        gain=1. if model is None else 10**(model.output_gain_db/20)
        desc.append(struct.pack('<HBBHH10f',n,len(rows),0,fi,bq_seen[key],scale,gain,*params,*([0.]*5)))
    if not fir_pool:fir_pool=[0,0]
    count=len(desc);labels=['OFF']+[s.label for s in project.slots]
    regions=[b''.join(desc),b''.join(s.encode('ascii').ljust(8,b'\0') for s in labels),
             np.array(fir_pool,dtype='<i2').tobytes(),np.array(bq_pool,dtype='<f4').tobytes(),
             GAIN_LUT.tobytes(),PRES_PARAMS.tobytes(),b'']
    offsets=[];offset=64
    for region in regions:offsets.append(offset);offset+=len(region)
    body=b''.join(regions)
    bank=HEADER.pack(MAGIC,4,offset,zlib.crc32(body),count,
                     max(32,max(struct.unpack_from('<H',d)[0] for d in desc)),
                     max(d[2] for d in desc),*offsets,len(fir_pool),len(bq_pool))+body
    report=validate(bank)
    report.update(schema='hybridir-rbj-bank/4',active_slots=len(project.slots),
                  owned_controls=[{'reso':b.name for b in s.model.sections if b.control_role=='reso'} for s in project.slots],
                  roles=['trained/default RESO','common PRES','exact remaining correction sections'],warnings=[])
    return bank,report


def validate(bank):
    if not 64<=len(bank)<=MAX_BYTES:raise ValueError('Invalid HVB4 length')
    h=HEADER.unpack_from(bank);magic,version,total,stamp,count,taps,bq=h[:7]
    if (magic,version,total)!=(MAGIC,4,len(bank)):raise ValueError('Invalid HVB4 header')
    if not 2<=count<=9 or not 32<=taps<=4096 or taps%4 or not 2<=bq<=32:
        raise ValueError('Invalid HVB4 capacities')
    nf,nq=h[14:]
    if nf>65534 or nf%2 or not 2<=nq<=65535:raise ValueError('Invalid HVB4 pools')
    offset=64
    for actual,length in zip(h[7:14],(48*count,8*count,2*nf,20*nq,244,12,0)):
        if actual!=offset or actual%4 or length>total-offset:raise ValueError('Invalid HVB4 region')
        offset+=length
    if offset!=total or zlib.crc32(bank[64:])!=stamp:raise ValueError('Invalid HVB4 stamp')
    if bank[h[11]:h[12]]!=GAIN_LUT.tobytes() or bank[h[12]:h[13]]!=PRES_PARAMS.tobytes():
        raise ValueError('Invalid HVB4 common control constants')
    seen=set()
    for i in range(count):
        n,q,flags,fi,qi,*floats=struct.unpack_from('<HBBHH10f',bank,h[7]+48*i)
        if n>taps or (n and (n<32 or n%4)) or not 2<=q<=bq or flags:raise ValueError('Invalid HVB4 descriptor')
        if fi%2 or fi+n>nf or qi+q>nq or not all(map(math.isfinite,floats)):raise ValueError('Invalid HVB4 bounds')
        params=tuple(floats[2:5])
        if params not in seen:validate_rbj(params);seen.add(params)
        if any(floats[5:]):raise ValueError('Nonzero HVB4 reserved fields')
        label=bank[h[8]+8*i:h[8]+8*(i+1)]
        if not label[0] or b'\0' not in label or any(c<32 or c>126 for c in label.split(b'\0')[0]):
            raise ValueError('Invalid HVB4 label')
    for offset in range(h[10],total,4):
        if not math.isfinite(struct.unpack_from('<f',bank,offset)[0]):raise ValueError('Non-finite HVB4 coefficient')
    for offset in range(h[10],h[10]+20*nq,20):
        if not stable_denominator(*struct.unpack_from('<2f',bank,offset+12)):raise ValueError('Unstable HVB4 denominator')
    return dict(bank_bytes=total,entry_count=count,max_fir=taps,max_bq=bq,
                fir_pool_samples=nf,bq_pool_sections=nq,control_table_bytes=0,
                gain_lut_bytes=244,common_pres_parameter_bytes=12,rbj_parameter_bytes=12*count,stamp=stamp)
