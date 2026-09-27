#ifndef HYBRID_BANK_V4_H
#define HYBRID_BANK_V4_H
#include <stdint.h>
#include "rbj_math.h"
/* Included after the generated, 8-aligned gj_bank bytes and gj_bank_meta.
 * Meta length is outside the bank and authenticated by the host patcher.
 * A loaded bank is immutable. Full validation occurs before first DSP use. */
typedef struct GjModelDesc {
    uint16_t fir_taps;
    uint8_t bq_count, flags;
    uint16_t fir_index, bq_index;
    float fir_scale, overall_gain;
    float depth_cw, depth_alpha, depth_A_nom;
    float pres_cw, pres_sw_half, pres_slope_term, pres_A_nom;
    float reserved;
} GjModelDesc;

#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_ALWAYS_INLINE(gj_v2_header)
#pragma FUNC_ALWAYS_INLINE(gj_v2_region)
#pragma FUNC_ALWAYS_INLINE(gj_v2_finite)
#pragma FUNC_ALWAYS_INLINE(gj_v2_stable)
#pragma FUNC_ALWAYS_INLINE(gj_v2_valid)
#pragma FUNC_ALWAYS_INLINE(gj_runtime_fir)
#pragma FUNC_ALWAYS_INLINE(gj_runtime_bq)
#pragma FUNC_ALWAYS_INLINE(gj_runtime_count)
#pragma FUNC_ALWAYS_INLINE(gj_enum_inverse)
#endif

static inline const volatile uint32_t *gj_v2_header(void) {
    return (const volatile uint32_t *)gj_bank;
}
static inline const unsigned char *gj_v2_region(unsigned int index) {
    return (const unsigned char *)gj_bank + gj_v2_header()[index];
}
static inline unsigned int gj_runtime_fir(void) { return gj_v2_header()[5]; }
static inline unsigned int gj_runtime_bq(void) { return gj_v2_header()[6]; }
static inline unsigned int gj_runtime_count(void) { return gj_v2_header()[4]; }
static inline float gj_enum_inverse(void) {
    union { float f; uint32_t u; } bits;
    bits.u=gj_bank_meta[2]; return bits.f;
}
static inline int gj_v2_finite(float x) {
    union { float f; uint32_t u; } bits;
    bits.f=x; return (bits.u & 0x7f800000u)!=0x7f800000u;
}
/* Jury inequalities, with 2^-20 margin for float32 table interpolation.
 * This bounds pole stability, not arbitrary signal/gain headroom. */
static inline int gj_v2_stable(const float *c) {
    float a1=c[3], a2=c[4], bound=(1.0f+a2)-0.00000095367431640625f;
    return a2>(-1.0f+0.00000095367431640625f) && a2<(1.0f-0.00000095367431640625f) &&
           a1<bound && -a1<bound;
}
#ifdef GJ_HOST_BANK
static unsigned int gj_host_validation_count;
#endif
static inline int gj_v2_valid(void) {
    const volatile uint32_t *h;
    uint32_t size=gj_bank_meta[1], count, nf, nq, end, lengths[7], i, k;
    const GjModelDesc *d;
    const char *label;
    const float *f;
#ifdef GJ_HOST_BANK
    ++gj_host_validation_count;
#endif
    if(!gj_bank || gj_bank_meta[0]!=0x344d4248u || size<64u || size>32768u || ((uintptr_t)gj_bank&7u)) return 0;
    h=gj_v2_header();
    if(h[0]!=0x34425648u || h[1]!=4u || h[2]!=size) return 0;
    count=h[4]; nf=h[14]; nq=h[15];
    if(count<2u || count>9u || h[5]<32u || h[5]>4096u || (h[5]&3u) || h[6]<2u || h[6]>32u) return 0;
    { float norm=gj_enum_inverse()*(float)(count-1u); if(!(norm>0.999999f && norm<1.000001f)) return 0; }
    if(nf>65534u || (nf&1u) || nq<2u || nq>65535u) return 0;
    lengths[0]=48u*count; lengths[1]=8u*count; lengths[2]=2u*nf;
    lengths[3]=20u*nq; lengths[4]=244u; lengths[5]=12u; lengths[6]=0u;
    end=64u;
    for(i=0u;i<7u;i++) {
        if(h[7u+i]!=end || (end&3u) || lengths[i]>size-end) return 0;
        end+=lengths[i];
    }
    if(end!=size) return 0;
    d=(const GjModelDesc *)gj_v2_region(7u);
    for(i=0u;i<count;i++) {
        uint32_t n=d[i].fir_taps, q=d[i].bq_count;
        if(n>h[5] || (n && (n<32u || (n&3u))) || q<2u || q>h[6] || d[i].flags) return 0;
        if((d[i].fir_index&1u) || (uint32_t)d[i].fir_index+n>nf || (uint32_t)d[i].bq_index+q>nq) return 0;
        f=&d[i].fir_scale;
        for(k=0u;k<10u;k++) if(!gj_v2_finite(f[k])) return 0;
        if(!(d[i].depth_cw>-1.0f && d[i].depth_cw<1.0f && d[i].depth_alpha>0.0f &&
             d[i].depth_alpha<1000000.0f && d[i].depth_A_nom>0.01f && d[i].depth_A_nom<100.0f)) return 0;
        for(k=5u;k<10u;k++) if(f[k]!=0.0f) return 0;
        label=(const char *)gj_v2_region(8u)+8u*i;
        if(!label[0]) return 0;
        for(k=0u;k<8u && label[k];k++) if(label[k]<32 || label[k]>126) return 0;
        if(k==8u) return 0;
    }
    f=(const float *)gj_v2_region(10u);
    for(i=0u;i<(size-h[10])/4u;i++) if(!gj_v2_finite(f[i])) return 0;
    for(i=0u;i<nq;i++) if(!gj_v2_stable(f+5u*i)) return 0;
    f=(const float *)gj_v2_region(11u);
    for(i=0u;i<61u;i++) if(!(f[i]>0.4f && f[i]<2.4f) || (i && !(f[i]>f[i-1u]))) return 0;
    if(f[30]!=1.0f) return 0;
    f=(const float *)gj_v2_region(12u);
    if(f[0]!=0.8782215714f || f[1]!=0.4782539904f || f[2]!=0.25f) return 0;
    return 1;
}

#define GJ_BANK_ENTRY_COUNT gj_runtime_count()
#define GJ_BANK_MAX_FIR gj_runtime_fir()
#define GJ_BANK_MAX_BQ gj_runtime_bq()
#define GJ_V2_DESC ((const GjModelDesc *)gj_v2_region(7u))
#define GJ_V2_LABELS ((const char (*)[8])gj_v2_region(8u))
#define GJ_V2_FIR ((const int16_t *)gj_v2_region(9u))
#define GJ_V2_BQ ((const float (*)[5])gj_v2_region(10u))
#define GJ_GAIN_LUT ((const float *)gj_v2_region(11u))
#define GJ_PRES_PARAMS ((const float *)gj_v2_region(12u))
#endif
