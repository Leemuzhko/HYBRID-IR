#ifndef GJ64H2_CORE_H
#define GJ64H2_CORE_H
#include <stdint.h>
#include "generated/bank_u1.h"
#define IR_MONO_TAPS GJ_BANK_MAX_FIR
#include "generated/kernel.h"

#define GJ_MAGIC 0x47483431u
#define GJ_MAX_BQ gj_runtime_bq()

typedef struct GjBranch {
    IrBlockState fir;
    float *z1, *z2;
    float rc[5], pc[5];
    float depth_pos, pres_pos, level_root, fade;
    uint32_t selection;
} GjBranch;

typedef struct GjState {
    uint32_t magic, stereo, bank_key, bank_size, bank_valid;
    uintptr_t bank_base, arena_base;
    uint32_t selected_l, selected_r, switch_phase;
    float switch_gain;
    GjBranch l, r;
} GjState;
/* Host supplies the arena; this code only validates and partitions it. */
#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_CANNOT_INLINE(gj_state_required)
#pragma FUNC_CANNOT_INLINE(gj_bind_state)
#endif
static inline uint32_t gj_state_required(void) {
    uint32_t taps, bq;
    if(!gj_bank || gj_bank_meta[0]!=0x344d4248u || gj_bank_meta[1]<64u || gj_bank_meta[1]>32768u || ((uintptr_t)gj_bank&7u)) return 0u;
    taps=gj_runtime_fir(); bq=gj_runtime_bq();
    if(taps<32u || taps>4096u || (taps&3u) || bq<2u || bq>32u) return 0u;
    return (uint32_t)sizeof(GjState)+2u*(4u*(taps+12u)+8u*bq);
}
static inline GjState *gj_bind_state(void *arena, uint32_t bytes) {
    uint32_t need=gj_state_required(), i, taps, bq, key=2166136261u;
    GjState *s=(GjState *)arena; float *data;
    if(!s || bytes<sizeof(GjState) || ((uintptr_t)s & (sizeof(void*)-1u))) return (GjState *)0;
    if(!need || bytes<need) return (GjState *)0;
    for(i=0u;i<16u;i++) key=(key^gj_v2_header()[i])*16777619u;
    key=(key^gj_bank_meta[2])*16777619u;
    if(s->bank_valid!=0x48564232u || s->bank_base!=(uintptr_t)gj_bank || s->arena_base!=(uintptr_t)arena ||
       s->bank_key!=key || s->bank_size!=gj_bank_meta[1]) {
        s->magic=0u; s->bank_valid=0u;
        if(!gj_v2_valid()) return (GjState *)0;
        s->bank_base=(uintptr_t)gj_bank; s->arena_base=(uintptr_t)arena;
        s->bank_key=key; s->bank_size=gj_bank_meta[1]; s->bank_valid=0x48564232u;
    }
    taps=gj_runtime_fir(); bq=gj_runtime_bq();
    data=(float *)((unsigned char *)s+sizeof(GjState));
    for(i=0;i<2u;i++) {
        GjBranch *branch=i?&s->r:&s->l;
        branch->fir.capacity=taps;
        branch->fir.history=data; data+=taps+12u;
        branch->z1=data; data+=bq; branch->z2=data; data+=bq;
    }
    return s;
}

#ifdef __TI_COMPILER_VERSION__
/* Share block/control work; the inner FIR MAC loop remains inlined. */
#pragma FUNC_CANNOT_INLINE(gj_clamp01)
#pragma FUNC_CANNOT_INLINE(gj_eq_position)
#pragma FUNC_CANNOT_INLINE(gj_select)
#pragma FUNC_ALWAYS_INLINE(gj_mode)
#pragma FUNC_CANNOT_INLINE(gj_smooth)
#pragma FUNC_CANNOT_INLINE(gj_gain_amplitude)
#pragma FUNC_CANNOT_INLINE(gj_reso_coeff)
#pragma FUNC_CANNOT_INLINE(gj_pres_coeff)
#pragma FUNC_CANNOT_INLINE(gj_level_root)
#pragma FUNC_CANNOT_INLINE(gj_reset_branch)
#pragma FUNC_ALWAYS_INLINE(gj_update_control)
#pragma FUNC_ALWAYS_INLINE(gj_coeff_identity)
#pragma FUNC_CANNOT_INLINE(gj_biquads)
#pragma FUNC_CANNOT_INLINE(gj_branch)
#pragma FUNC_ALWAYS_INLINE(gj_process)
#endif

static inline float gj_clamp01(float x, float fallback) {
    if (!(x >= 0.0f)) return fallback;
    return x > 1.0f ? 1.0f : x;
}

static inline float gj_eq_position(float raw) {
    float ui, nearest, error;
    /* LineSel mode-0 mapper: 1.5 * UI / (151-1), verified by original
       C674 execution. EQ UI 0..60 must span the full 0..1 table domain. */
    if (!(raw >= 0.0f)) return 0.5f;
    if (raw >= 0.6f) return 1.0f;
    ui=raw*100.0f;
    nearest=(float)(int)(ui+0.5f);
    error=ui-nearest;
    /* Remove mapper rounding at discrete positions, notably neutral 30.
       Preserve intermediate values delivered by the firmware ramp. */
    if(error<0.0001f && error>-0.0001f) ui=nearest;
    return ui*(1.0f/60.0f);
}

static inline unsigned int gj_select(float raw) {
    unsigned int v;
    /* LineSel i/100 (verified mapper) and legacy normalized i/(count-1).
       Authoring remains capped at 8 active slots to keep grids disjoint. */
    if (!(raw >= 0.0f) || raw > 1.0f) return 1u;
    for(v=0u;v<GJ_BANK_ENTRY_COUNT;v++)
        if(raw >= (float)v*.01f-.0001f && raw <= (float)v*.01f+.0001f) return v;
    for(v=0u;v<GJ_BANK_ENTRY_COUNT;v++) {
        float value=(float)v*gj_enum_inverse();
        if(raw >= value-.0001f && raw <= value+.0001f) return v;
    }
    return 1u;
}

static inline unsigned int gj_mode(float raw) {
    unsigned int v;
    if (!(raw >= 0.0f) || raw > 1.0f) return 1u;
    for(v=0u;v<4u;v++) {
        float saved=(float)v*.01f, live=(float)v*(1.0f/3.0f);
        if((raw >= saved-.0001f && raw <= saved+.0001f) ||
           (raw >= live-.0001f && raw <= live+.0001f)) return v;
    }
    return 1u;
}

static inline float gj_smooth(float old, float target) {
    float d=target-old;
    if(d<0.00001f && d>-0.00001f) return target;
    return old+0.025f*d;
}

static inline float gj_gain_amplitude(float position) {
    float x=60.0f*gj_clamp01(position,0.5f);
    int i=(int)x;
    float frac;
    if(i>=60){i=59;frac=1.0f;}else frac=x-(float)i;
    return GJ_GAIN_LUT[i]+frac*(GJ_GAIN_LUT[i+1]-GJ_GAIN_LUT[i]);
}
static inline void gj_reso_coeff(float position,const GjModelDesc *d,float *dst) {
    const float *base=&GJ_V2_BQ[d->bq_index][0];unsigned int k;
    if(position!=0.5f) {
        gj_rbj_peak(d->depth_cw,d->depth_alpha,d->depth_A_nom*gj_gain_amplitude(position),dst);
        if(gj_v2_stable(dst)) return;
    }
    /* Nominal is byte-exact imported SOS. Unsafe float32 extremes fall back
       to it rather than applying an unstable ramp coefficient. */
    for(k=0u;k<5u;k++) dst[k]=base[k];
}
static inline void gj_pres_coeff(float position,float *dst) {
    if(position!=0.5f) {
        gj_rbj_pres(GJ_PRES_PARAMS[0],GJ_PRES_PARAMS[1],GJ_PRES_PARAMS[2],gj_gain_amplitude(position),dst);
        if(gj_v2_stable(dst)) return;
    }
    dst[0]=1.0f;dst[1]=0.0f;dst[2]=0.0f;dst[3]=0.0f;dst[4]=0.0f;
}

static inline float gj_level_root(float raw) {
    /* Hardware LineSel-style materialization: UI 100 -> 1.0f, 150 -> 1.5f. */
    if (!(raw >= 0.0f)) return 0.0f;
    return raw > 1.5f ? 1.5f : raw;
}

static inline void gj_reset_branch(GjBranch *s,float level,float depth,float pres) {
    unsigned int i;
    s->fir.magic=0u;s->selection=99u;
    s->depth_pos=depth;s->pres_pos=pres;s->level_root=level;s->fade=0.0f;
    for(i=0u;i<GJ_MAX_BQ;i++){s->z1[i]=0.0f;s->z2[i]=0.0f;}
}

static inline void gj_update_control(GjBranch *s,const GjModelDesc *d,float depth,float pres,int force) {
    float nd=gj_smooth(s->depth_pos,depth), np=gj_smooth(s->pres_pos,pres);
    if(force || nd!=s->depth_pos) gj_reso_coeff(nd,d,s->rc);
    if(force || np!=s->pres_pos) gj_pres_coeff(np,s->pc);
    s->depth_pos=nd;s->pres_pos=np;
}

static inline int gj_coeff_identity(const float *c) {
    return c[0]==1.0f && c[1]==0.0f && c[2]==0.0f && c[3]==0.0f && c[4]==0.0f;
}

static inline void gj_biquads(GjBranch *s,float *x,unsigned int nb,const float *base) {
    unsigned int j,i;
    for(j=0u;j<nb;j++) {
        const float *c=j==0u?s->rc:(j==1u?s->pc:base+j*5u);
        float b0,b1,b2,a1,a2,z1,z2;
        if(gj_coeff_identity(c)){s->z1[j]=0.0f;s->z2[j]=0.0f;continue;}
        b0=c[0];b1=c[1];b2=c[2];a1=c[3];a2=c[4];z1=s->z1[j];z2=s->z2[j];
#ifdef __TI_COMPILER_VERSION__
#pragma MUST_ITERATE(8,8,8)
#endif
        for(i=0u;i<8u;i++) {
            float v=x[i],y=b0*v+z1;
            z1=b1*v-a1*y+z2;z2=b2*v-a2*y;x[i]=y;
        }
        s->z1[j]=z1;s->z2[j]=z2;
    }
}

static inline void gj_branch(GjBranch *s,float *fx,unsigned int sel,float level_raw,float depth_raw,float pres_raw,unsigned int channel) {
    unsigned int i,base_index=channel==2u?8u:0u;
    float target=gj_level_root(level_raw),depth=gj_clamp01(depth_raw,.5f),pres=gj_clamp01(pres_raw,.5f);
    const GjModelDesc *d;const float *bq;int changed;
    if(sel>=GJ_BANK_ENTRY_COUNT)sel=1u;
    changed=(s->selection!=sel);d=&GJ_V2_DESC[sel];bq=&GJ_V2_BQ[d->bq_index][0];
    if(changed){
        s->fir.magic=0u;s->selection=sel;s->fade=0.0f;s->depth_pos=depth;s->pres_pos=pres;
        for(i=0u;i<GJ_MAX_BQ;i++){s->z1[i]=0.0f;s->z2[i]=0.0f;}
    }
    gj_update_control(s,d,depth,pres,changed);
    if(d->fir_taps){
        const int16_t *fir=GJ_V2_FIR+d->fir_index;
        /* Each branch owns a fixed lane and independent history. Present that
           lane as mono-left so the FIR need not contain unused mix/right paths. */
        ir_block_process(&s->fir,fx+base_index,1,d->fir_scale,0u,fir,d->fir_taps);
    }else s->fir.magic=0u;
    gj_biquads(s,fx+base_index,d->bq_count,bq);
    for(i=0u;i<8u;i++){
        float dd=target-s->level_root,g;
        if(dd<0.00001f && dd>-0.00001f)s->level_root=target;else s->level_root+=0.002f*dd;
        if(s->fade<1.0f){s->fade+=0.0078125f;if(s->fade>1.0f)s->fade=1.0f;}
        g=(s->level_root*s->level_root)*s->fade*d->overall_gain;
        fx[base_index+i]*=g;
    }
}

static inline void gj_process(GjState *s,float *fx,int enabled,float ll,unsigned int stereo,float lr,unsigned int lsel,float ld,float lp,unsigned int rsel,float rd,float rp) {
    unsigned int i;
    if(!fx)return;if(!enabled){if(s)s->magic=0u;return;}if(!s)return;
    /* 0=STR, 1=MIX, 2=L, 3=R. All non-STR inputs are (L+R)/2. */
    if(stereo>3u)stereo=1u;if(lsel>=GJ_BANK_ENTRY_COUNT)lsel=1u;if(rsel>=GJ_BANK_ENTRY_COUNT)rsel=1u;
    if(s->magic!=GJ_MAGIC){
        s->magic=GJ_MAGIC;s->stereo=stereo;
        s->selected_l=lsel;s->selected_r=rsel;s->switch_phase=0u;s->switch_gain=1.0f;
        gj_reset_branch(&s->l,gj_level_root(ll),gj_clamp01(ld,.5f),gj_clamp01(lp,.5f));
        gj_reset_branch(&s->r,gj_level_root(lr),gj_clamp01(rd,.5f),gj_clamp01(rp,.5f));
    }
    /* Switch at zero gain, never run old/new FIR concurrently. Inactive IR
       changes are remembered at the next actual routing switch. */
    if(s->switch_phase!=2u && (s->stereo!=stereo ||
       (s->stereo!=3u && s->selected_l!=lsel) ||
       (s->stereo!=2u && s->selected_r!=rsel))) s->switch_phase=1u;
    if(s->switch_phase==1u && s->switch_gain<=0.0f){
        s->stereo=stereo;s->selected_l=lsel;s->selected_r=rsel;s->switch_phase=2u;
        gj_reset_branch(&s->l,gj_level_root(ll),gj_clamp01(ld,.5f),gj_clamp01(lp,.5f));
        gj_reset_branch(&s->r,gj_level_root(lr),gj_clamp01(rd,.5f),gj_clamp01(rp,.5f));
    }
    stereo=s->stereo;lsel=s->selected_l;rsel=s->selected_r;
    if(stereo!=0u){for(i=0u;i<8u;i++){float m=.5f*fx[i]+.5f*fx[i+8u];fx[i]=m;fx[i+8u]=m;}}
    if(stereo!=3u)gj_branch(&s->l,fx,lsel,ll,ld,lp,0u);
    if(stereo!=2u)gj_branch(&s->r,fx,rsel,lr,rd,rp,2u);
    if(stereo==1u){for(i=0u;i<8u;i++){float m=.5f*(fx[i]+fx[i+8u]);fx[i]=m;fx[i+8u]=m;}}
    else if(stereo==2u){for(i=0u;i<8u;i++)fx[i+8u]=fx[i];}
    else if(stereo==3u){for(i=0u;i<8u;i++)fx[i]=fx[i+8u];}
    if(s->switch_phase){
        for(i=0u;i<8u;i++){
            if(s->switch_phase==1u){s->switch_gain-=0.015625f;if(s->switch_gain<0.0f)s->switch_gain=0.0f;}
            else {s->switch_gain+=0.0078125f;if(s->switch_gain>1.0f)s->switch_gain=1.0f;}
            fx[i]*=s->switch_gain;fx[i+8u]*=s->switch_gain;
        }
        if(s->switch_phase==2u && s->switch_gain>=1.0f)s->switch_phase=0u;
    }
}
#endif
