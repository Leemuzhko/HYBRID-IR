#ifndef HYBRID_RBJ_MATH_H
#define HYBRID_RBJ_MATH_H
#ifdef __TI_COMPILER_VERSION__
#include <c6x.h>
#pragma FUNC_ALWAYS_INLINE(gj_recip)
#pragma FUNC_ALWAYS_INLINE(gj_sqrt)
#pragma FUNC_ALWAYS_INLINE(gj_rbj_peak)
#pragma FUNC_ALWAYS_INLINE(gj_rbj_pres)
#else
#include <math.h>
#endif

/* Positive normal operands only, bounded by bank validation. Two Newton
 * steps refine C674 approximate reciprocal / reciprocal-square-root.
 * Host math is a reference and is not a model of the intrinsic's first bits. */
static inline float gj_recip(float x) {
#ifdef __TI_COMPILER_VERSION__
    float y=_rcpsp(x);
    y=y*(2.0f-x*y);return y*(2.0f-x*y);
#else
    return 1.0f/x;
#endif
}
static inline float gj_sqrt(float x) {
#ifdef __TI_COMPILER_VERSION__
    float y=_rsqrsp(x);
    y=y*(1.5f-0.5f*x*y*y);y=y*(1.5f-0.5f*x*y*y);return x*y;
#else
    return sqrtf(x);
#endif
}
static inline void gj_rbj_peak(float cw,float alpha,float a,float *c) {
    float v=alpha*gj_recip(a),r=gj_recip(1.0f+v),c1=-2.0f*cw*r;
    c[0]=(1.0f+alpha*a)*r;c[1]=c1;c[2]=(1.0f-alpha*a)*r;
    c[3]=c1;c[4]=(1.0f-v)*r;
}
static inline void gj_rbj_pres(float cw,float sw,float slope,float a,float *c) {
    float beta=sw*gj_sqrt((a*a+1.0f)*slope+2.0f*a);
    float ap=a+1.0f,am=a-1.0f,amcw=am*cw,apcw=ap*cw;
    float r=gj_recip(ap-amcw+beta);
    c[0]=a*(ap+amcw+beta)*r;c[1]=(-2.0f*a)*(am+apcw)*r;
    c[2]=a*(ap+amcw-beta)*r;c[3]=2.0f*(am-apcw)*r;c[4]=(ap-amcw-beta)*r;
}
#endif
