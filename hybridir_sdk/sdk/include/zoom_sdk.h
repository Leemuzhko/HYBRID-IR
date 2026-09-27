#ifndef ZOOM_SDK_H
#define ZOOM_SDK_H

/*
 * Minimal hardware-facing SDK surface for Zoom ZDL effects.
 *
 * Confirmed audio callback layout:
 *   ctx[1]  -> parameter float table
 *   ctx[4]  -> host-provided dry/auxiliary buffer (shared and writable)
 *   ctx[5]  -> current effect buffer
 *   ctx[6]  -> output accumulator
 *   ctx[11] / ctx[12] -> host shuttle that must be preserved
 *
 * Each callback processes 16 float samples:
 *   samples 0..7   = left
 *   samples 8..15  = right
 */

#include <stdint.h>

#define ZOOM_BLOCK_SAMPLES 16
#define ZOOM_CHANNEL_SAMPLES 8

#define ZOOM_CTX_PARAMS 1
#define ZOOM_CTX_STATE_DESCRIPTOR 3
#define ZOOM_CTX_DRY_BUFFER 4
#define ZOOM_CTX_EFFECT_BUFFER 5
#define ZOOM_CTX_OUTPUT_BUFFER 6
#define ZOOM_CTX_SHUTTLE_DST 11
#define ZOOM_CTX_SHUTTLE_SRC 12

#define ZOOM_PARAM_ONOFF 0
#define ZOOM_PARAM_FIRST_USER 5
#define ZOOM_MAX_STATE_ARENA_BYTES 0x00800000u

#define ZOOM_PTR(type, word) ((type)(uintptr_t)(word))

#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_ALWAYS_INLINE(zoom_clamp01)
#endif
static inline float zoom_clamp01(float value)
{
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
}

/*
 * Hardware-confirmed on MS-70CDR SYSTEM 2.10 with the current two-parameter
 * stock-derived handlers: user slots contain normalized 0..1 floats.
 */
#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_ALWAYS_INLINE(zoom_param01)
#endif
static inline float zoom_param01(float raw)
{
    return zoom_clamp01(raw);
}

/*
 * Legacy probe conversion retained for reproducing older experiments. Do not
 * use it for the current SDK handler configuration: it saturates at UI 14.
 */
static inline float zoom_linesel_param01(float raw)
{
    return zoom_clamp01(raw * 7.1428571f);
}

static inline float *zoom_params(unsigned int *ctx)
{
    return ZOOM_PTR(float *, ctx[ZOOM_CTX_PARAMS]);
}

static inline float *zoom_effect_buffer(unsigned int *ctx)
{
    return ZOOM_PTR(float *, ctx[ZOOM_CTX_EFFECT_BUFFER]);
}

static inline float *zoom_dry_buffer(unsigned int *ctx)
{
    return ZOOM_PTR(float *, ctx[ZOOM_CTX_DRY_BUFFER]);
}

static inline float *zoom_output_buffer(unsigned int *ctx)
{
    return ZOOM_PTR(float *, ctx[ZOOM_CTX_OUTPUT_BUFFER]);
}

/*
 * Return an aligned base inside the host-managed ctx[3] arena, or NULL when
 * the descriptor is absent, malformed, too small, or implausibly large.
 */
static inline void *zoom_state_arena(
    unsigned int *ctx,
    uint32_t required_bytes
)
{
    volatile unsigned int *desc = ZOOM_PTR(
        volatile unsigned int *,
        ctx[ZOOM_CTX_STATE_DESCRIPTOR]
    );
    uintptr_t base;
    uintptr_t end;
    uintptr_t bytes;
    uintptr_t aligned_base;
    unsigned int span;

    if (!desc) {
        return (void *)0;
    }
    base = (uintptr_t)desc[0];
    end = (uintptr_t)desc[1];
    span = desc[2];
    if (base == 0u || end <= base) {
        return (void *)0;
    }
    if ((base & 3u) != 0u || (end & 3u) != 0u || (span & 3u) != 0u) {
        return (void *)0;
    }

    bytes = end - base;
    if (bytes < required_bytes || bytes > ZOOM_MAX_STATE_ARENA_BYTES) {
        return (void *)0;
    }
    if (span < bytes || span > ZOOM_MAX_STATE_ARENA_BYTES) {
        return (void *)0;
    }

    aligned_base = (base + 3u) & ~(uintptr_t)3u;
    if (aligned_base + required_bytes > end) {
        return (void *)0;
    }
    return (void *)aligned_base;
}

static inline void zoom_preserve_host_shuttle(unsigned int *ctx)
{
    unsigned int *src = ZOOM_PTR(unsigned int *, ctx[ZOOM_CTX_SHUTTLE_SRC]);
    unsigned int *dst_ptr = ZOOM_PTR(
        unsigned int *,
        ctx[ZOOM_CTX_SHUTTLE_DST]
    );
    unsigned int *dst = ZOOM_PTR(unsigned int *, *dst_ptr);
    *dst = *src;
}

#endif
