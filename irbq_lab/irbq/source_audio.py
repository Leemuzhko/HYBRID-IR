"""Bounded, byte-exact source audio. Never execute or extract archive paths."""
import hashlib
import io
import numpy as np
import soundfile as sf


def decode_source(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 32_000_000:
        raise ValueError('Invalid source audio size')
    with sf.SoundFile(io.BytesIO(raw)) as audio:
        if (not 8000 <= audio.samplerate <= 192000 or not 1 <= audio.channels <= 8
                or not 0 < audio.frames <= 30*audio.samplerate
                or audio.frames*audio.channels > 6_000_000):
            raise ValueError('Source audio exceeds sample/rate/channel limits')
        meta=dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                  frames=audio.frames, channels=audio.channels, fs=audio.samplerate,
                  format=audio.format, subtype=audio.subtype)
        samples=audio.read(dtype='float64')
    if not np.all(np.isfinite(samples)):raise ValueError('Non-finite source audio')
    return samples, meta['fs'], meta
