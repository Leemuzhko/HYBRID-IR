#ifndef IR_BLOCK_CORE_H
#define IR_BLOCK_CORE_H
#include <stdint.h>
#define IR_BLOCK_CAPACITY (IR_MONO_TAPS + 8u)
#define IR_BLOCK_MAGIC 0x49525234u
#define IR_BLOCK_CLEAR 1032u
#define IR_BLOCK_STORAGE (IR_BLOCK_CAPACITY + 4u)

/* Eight spare samples keep older outputs valid while four new inputs enter.
 * Only the first four samples are duplicated past the end of the ring.
 * They cover the four-output read at the seam; all other history is single-copy. */
typedef struct IrBlockState {
    uint32_t magic, version, clear_cursor, write_index, active, mode;
    float history[IR_BLOCK_STORAGE];
} IrBlockState;

#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_ALWAYS_INLINE(ir_block_mode)
#endif
static inline unsigned int ir_block_mode(float raw)
{
    /* Same normalized/percent-shaped enum encodings as the working mono build. */
    if (!(raw >= 0.0f)) return 1u;
    if (raw <= 0.025f) {
        if (raw < 0.005f) return 0u;
        return raw < 0.015f ? 1u : 2u;
    }
    if (raw < 0.25f) return 0u;
    return raw < 0.75f ? 1u : 2u;
}

#ifdef __TI_COMPILER_VERSION__
#pragma FUNC_ALWAYS_INLINE(ir_block_process)
#endif
static inline void ir_block_process(
    IrBlockState *state, float *fx, int enabled, float level, unsigned int mode, const int16_t *coefficients, unsigned int taps)
{
    uint32_t i, w;
    if (mode > 2u) mode = 1u;
    if (state->magic != IR_BLOCK_MAGIC || state->version != IR_MONO_TAPS) {
        state->magic = IR_BLOCK_MAGIC;
        state->version = IR_MONO_TAPS;
        state->clear_cursor = 0u;
        state->write_index = 0u;
        state->active = 0u;
        state->mode = mode;
    }
    if (!enabled || state->mode != mode) {
        state->active = 0u;
        state->clear_cursor = 0u;
        state->mode = mode;
        if (!enabled) return;
    }
    if (!state->active) {
        uint32_t end = state->clear_cursor + IR_BLOCK_CLEAR;
        if (end > IR_BLOCK_STORAGE) end = IR_BLOCK_STORAGE;
        for (i = state->clear_cursor; i < end; ++i) state->history[i] = 0.0f;
        state->clear_cursor = end;
        if (end != IR_BLOCK_STORAGE) {
            for (i = 0u; i < 8u; ++i) {
                if (mode != 2u) fx[i] = 0.0f;
                if (mode != 0u) fx[i + 8u] = 0.0f;
            }
            return;
        }
        state->write_index = 0u;
        state->active = 1u;
    }
    w = state->write_index;
    for (i = 0u; i < 8u; i += 4u) {
        uint32_t j, k;
        float a0 = 0.0f, a1 = 0.0f, b0 = 0.0f, b1 = 0.0f;
        float c0 = 0.0f, c1 = 0.0f, d0 = 0.0f, d1 = 0.0f;
        const float *history;
        w = w >= 4u ? w - 4u : IR_BLOCK_CAPACITY - 4u;
        for (j = 0u; j < 4u; ++j) {
            float input;
            uint32_t slot = w + 3u - j;
            if (mode == 0u) input = fx[i + j];
            else if (mode == 2u) input = fx[i + j + 8u];
            else input = 0.5f * fx[i + j] + 0.5f * fx[i + j + 8u];
            state->history[slot] = input;
            if (slot < 4u) state->history[slot + IR_BLOCK_CAPACITY] = input;
        }
        history = state->history + w;
        /* Four outputs reuse each coefficient and adjacent history samples.
         * Eight accumulators break the floating-add dependency chains. */
        k = 0u;
        j = IR_BLOCK_CAPACITY - w;
        /* At most two linear spans. Both lengths are even (in fact multiples
         * of four), so the same accumulator order survives the ring seam.
         * The four-sample guard makes history[t+4] safe at the first span end. */
        while (k < taps) {
            uint32_t t;
            if (j > taps - k) j = taps - k;
            for (t = 0u; t < j; t += 2u) {
                /* Q15 storage only; history and accumulation stay float32.
                 * Normalization is baked into these integers at build time. */
                float h0 = (float)coefficients[k + t] * (1.0f / 32768.0f);
                float h1 = (float)coefficients[k + t + 1u] * (1.0f / 32768.0f);
                float x0 = history[t], x1 = history[t + 1u];
                float x2 = history[t + 2u], x3 = history[t + 3u];
                float x4 = history[t + 4u];
                a0 += h0 * x3; a1 += h1 * x4;
                b0 += h0 * x2; b1 += h1 * x3;
                c0 += h0 * x1; c1 += h1 * x2;
                d0 += h0 * x0; d1 += h1 * x1;
            }
            k += j;
            history = state->history;
            j = IR_BLOCK_CAPACITY;
        }
        a0 = (a0 + a1) * level;
        b0 = (b0 + b1) * level;
        c0 = (c0 + c1) * level;
        d0 = (d0 + d1) * level;
        if (mode != 2u) {
            fx[i] = a0; fx[i + 1u] = b0; fx[i + 2u] = c0; fx[i + 3u] = d0;
        }
        if (mode != 0u) {
            fx[i + 8u] = a0; fx[i + 9u] = b0;
            fx[i + 10u] = c0; fx[i + 11u] = d0;
        }
    }
    state->write_index = w;
}
#endif
