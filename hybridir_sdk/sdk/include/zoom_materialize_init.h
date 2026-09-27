/*
 * Load-time materialization for saved Zoom MS-series parameters.
 *
 * This header is injected by sdk/build_effect.py when a manifest sets
 * "materialize_saved_params": true. The build supplies:
 *
 *   ZOOM_MATERIALIZE_INIT_FUNCTION
 *   ZOOM_MATERIALIZE_PARAM_COUNT
 *
 * Hardware proof:
 *   RAWMAP v1.01  - one parameter
 *   MAP3SDK v1.00 - three parameters
 *
 * Firmware-specific contract (MS-70CDR SYSTEM 2.10):
 *   saved row   = 0xC009C1A0 + 44 * state[0]
 *   knob column = 2 + parameter index
 *   live target = ((float *)state[1])[5 + parameter index]
 *   mapper      = state[21]
 */

#ifndef ZOOM_MATERIALIZE_INIT_FUNCTION
#error "ZOOM_MATERIALIZE_INIT_FUNCTION must name the generated init function"
#endif

#ifndef ZOOM_MATERIALIZE_PARAM_COUNT
#error "ZOOM_MATERIALIZE_PARAM_COUNT must contain the user parameter count"
#endif

#define ZOOM_MAT_STRINGIFY_INNER(value) #value
#define ZOOM_MAT_STRINGIFY(value) ZOOM_MAT_STRINGIFY_INNER(value)

/*
 * Keep every block structurally identical to RAWMAP v1.01. In particular,
 * use the stock-derived __c6xabi_call_stub instead of allowing the compiler
 * to choose a different indirect-call sequence.
 */
#define ZOOM_MATERIALIZE_ONE(saved_column, live_index)                   \
    asm("        LDW.D1T1  *+A10[0], A0");                              \
    asm("        MVK.S1    44, A1");                                    \
    asm("        MVKL.S1   0xC009C1A0, A2");                            \
    asm("        MVKH.S1   0xC009C1A0, A2");                            \
    asm("        NOP       2");                                         \
    asm("        MPY32.M1  A1, A0, A1");                               \
    asm("        NOP       3");                                         \
    asm("        ADD.L1    A2, A1, A2");                               \
    asm("        LDW.D1T1  *+A2[" ZOOM_MAT_STRINGIFY(saved_column)      \
        "], A8");                                                       \
    asm("        LDW.D1T2  *+A10[21], B31");                            \
    asm("        MVK.S1    255, A4");                                   \
    asm("        SHL.S1    A4, 22, A4");                               \
    asm("        MVK.L2    0, B4");                                     \
    asm("        MVK.S1    151, A6");                                   \
    asm("        MVK.L2    0, B6");                                     \
    asm("        NOP       4");                                         \
    asm("        CALLP.S2  __c6xabi_call_stub, B3");                    \
    asm("        NOP       5");                                         \
    asm("        LDW.D1T1  *+A10[1], A0");                              \
    asm("        NOP       5");                                         \
    asm("        STW.D1T1  A4, *+A0["                                  \
        ZOOM_MAT_STRINGIFY(live_index) "]")

asm("        .sect \".text\"");
asm("        .global "
    ZOOM_MAT_STRINGIFY(ZOOM_MATERIALIZE_INIT_FUNCTION));
asm("        .ref __c6xabi_call_stub");
asm("        .ref __c6xabi_pop_rts");
asm("        .ref __c6xabi_push_rts");
asm(ZOOM_MAT_STRINGIFY(ZOOM_MATERIALIZE_INIT_FUNCTION) ":");
asm("        CALLP.S1  __c6xabi_push_rts, A3");
asm("        MV.L1     A4, A10");

#if ZOOM_MATERIALIZE_PARAM_COUNT >= 1
ZOOM_MATERIALIZE_ONE(2, 5);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 2
ZOOM_MATERIALIZE_ONE(3, 6);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 3
ZOOM_MATERIALIZE_ONE(4, 7);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 4
ZOOM_MATERIALIZE_ONE(5, 8);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 5
ZOOM_MATERIALIZE_ONE(6, 9);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 6
ZOOM_MATERIALIZE_ONE(7, 10);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 7
ZOOM_MATERIALIZE_ONE(8, 11);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 8
ZOOM_MATERIALIZE_ONE(9, 12);
#endif
#if ZOOM_MATERIALIZE_PARAM_COUNT >= 9
ZOOM_MATERIALIZE_ONE(10, 13);
#endif

asm("        CALLP.S1  __c6xabi_pop_rts, A3");
asm("        NOP       2");

#undef ZOOM_MATERIALIZE_ONE
#undef ZOOM_MAT_STRINGIFY
#undef ZOOM_MAT_STRINGIFY_INNER
