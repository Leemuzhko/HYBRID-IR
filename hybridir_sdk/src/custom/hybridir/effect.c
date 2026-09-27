#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_ALWAYS_INLINE(zoom_preserve_host_shuttle)
#pragma FUNC_ALWAYS_INLINE(zoom_state_arena)
#pragma FUNC_ALWAYS_INLINE(zoom_params)
#pragma FUNC_ALWAYS_INLINE(zoom_effect_buffer)
#pragma FUNC_ALWAYS_INLINE(gj_process_params)
#endif
#include "zoom_sdk.h"
#include "core.h"

#ifdef __TI_COMPILER_VERSION__
#pragma CODE_SECTION(GetString_GjIR, ".text")
#pragma CODE_SECTION(GetString_GjMode, ".text")
#pragma CODE_SECTION(GetString_GjEQ, ".text")
#pragma CODE_SECTION(Fx_FLT_HYBRIDIR, ".audio")
#endif

int GetString_GjIR(unsigned int v, char *s) {
    unsigned int i=0u;
    const char *p;
    if (v>=GJ_BANK_ENTRY_COUNT) v=1u;
    p=&gj_bank.labels[v][0];
    while(i<7u && p[i]) { s[i]=p[i]; ++i; }
    s[i]=0;
    return (int)i;
}

int GetString_GjMode(unsigned int v, char *s) {
    if(v==0u){s[0]='S';s[1]='T';s[2]='R';s[3]=0;return 3;}
    if(v==2u || v==3u){s[0]=v==2u?'L':'R';s[1]=0;return 1;}
    s[0]='M';s[1]='I';s[2]='X';s[3]=0;return 3;
}

/* v=0..60 -> -15..+15 dB in 0.5 dB steps. Display intentionally omits dB. */
int GetString_GjEQ(unsigned int v, char *s) {
    int half_db, a, whole, n=0;
    if(v>60u)v=60u;
    half_db=(int)v-30;
    if(half_db==0){s[0]='0';s[1]='.';s[2]='0';s[3]=0;return 3;}
    if(half_db<0){s[n++]='-';a=-half_db;}else{s[n++]='+';a=half_db;}
    whole=a/2;
    if(whole>=10){s[n++]=(char)('0'+whole/10);s[n++]=(char)('0'+whole%10);}
    else{s[n++]=(char)('0'+whole);}
    s[n++]='.';s[n++]=(a&1)?'5':'0';
    s[n]=0;return n;
}

static inline void gj_process_params(GjState *s, float *fx, const float *p) {
    gj_process(s,fx,p[ZOOM_PARAM_ONOFF]>=0.5f,
        p[5],gj_mode(p[6]),p[7],gj_select(p[8]),gj_eq_position(p[9]),gj_eq_position(p[10]),
        gj_select(p[11]),gj_eq_position(p[12]),gj_eq_position(p[13]));
}

void Fx_FLT_HYBRIDIR(unsigned int *ctx) {
    GjState *s; float *p;
    zoom_preserve_host_shuttle(ctx);
    s=(GjState *)zoom_state_arena(ctx,(uint32_t)sizeof(GjState));
    p=zoom_params(ctx);
    gj_process_params(s,zoom_effect_buffer(ctx),p);
}
