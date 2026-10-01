"""Exercise real bundled code with synthetic data; never the user's settings/banks."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile


def require(value, message):
    if not value:
        raise AssertionError(message)


def run(work: Path, make_window):
    import numpy as np
    import soundfile as sf
    from PIL import Image
    from .app_paths import application_root, safe_output_directory
    from .dsp import Model, PrepConfig, prepare, response_normalization_power
    from .trainer import train, TrainConfig
    from .project import Session, export_model
    from .authoring import portable_bank_bytes, load_portable_bank
    from .audio import render_ab
    from .preferences import settings_path
    from .template_profile import load_package
    from .template_patch import patch_project
    from .zoom_bank import SDK, BankProject, Slot
    from . import __version__
    require(settings_path() == work/'settings.json', 'Self-test did not isolate settings')
    package = load_package(SDK/'templates/HIR3A.template.json')
    require(hashlib.sha256(package.raw).hexdigest() == '14f605e66ea0ca24a1bd0b0873cb15b8dbaf900290ffe78f9f6cb60c99b0f9d4', 'HIR3A bytes changed')
    if getattr(sys, 'frozen', False):
        require(SDK.resolve().is_relative_to(application_root().parent.resolve()), 'SDK escaped application bundle')
    h = np.exp(-np.arange(64)/8.) * np.cos(np.arange(64)*.3)
    modes = ('k_weighted', 'k_band', 'k_pink', 'k_pink_band')
    for mode in modes:
        out, _, _ = prepare(h, 44100, PrepConfig(trim_start=False, minimum_phase=False, normalization=mode, level_db=-3))
        H = np.fft.rfft(out, 65536); f = np.fft.rfftfreq(65536, 1/44100)
        require(abs(10*np.log10(response_normalization_power(H, f, 44100, mode))+3) < 1e-8, 'K-weighted level error')
    wav = work/'source.wav'; sf.write(wav, h, 44100, subtype='FLOAT')
    session = Session(); session.load_audio(wav); original = session.source_audio
    session.config = PrepConfig(trim_start=False, minimum_phase=False, normalization='k_pink_band')
    session.preprocess()
    session.model = train(session.target, Model(44100, np.r_[1.,np.zeros(63)], []), TrainConfig(mode='fir'))
    require(np.all(np.isfinite(session.model.fir)), 'FIR training is non-finite')
    project_file = work/'roundtrip.irbq'; session.save(project_file)
    recovered = Session.load(project_file)
    require(recovered.source_audio == original == wav.read_bytes(), 'Original WAV changed')
    export_model(work/'model', recovered)
    bank = BankProject(name='MAC TEST', filename='MACTEST', fxid=901, slots=[Slot('UNIT', recovered.model)])
    bank_file = work/'roundtrip.hybridbank'; bank_file.write_bytes(portable_bank_bytes(bank))
    restored = load_portable_bank(bank_file)
    require(len(restored.slots) == 1, 'Bank roundtrip failed')
    # Use the raw OS temporary alias, not a canonical-TEMP workaround.
    with tempfile.TemporaryDirectory(prefix='hybridir-native-export-') as raw_temp:
        raw_path = Path(raw_temp)
        path, receipt = patch_project(restored, raw_path, profile_path=package.profile_path, allow_experimental=True)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == receipt['sha256'], 'ZDL checksum mismatch')
        with Image.open(path.with_suffix('.png')) as im:
            require(im.size == (128,96) and im.mode == 'RGBA', 'Manager artwork is invalid')
        outside = raw_path/'outside'; outside.mkdir()
        linked = raw_path/'user-link'; linked.symlink_to(outside, target_is_directory=True)
        try:
            safe_output_directory(linked/'export')
        except ValueError:
            pass
        else:
            raise AssertionError('User symlink unexpectedly accepted')
        require(not list(outside.iterdir()), 'Unsafe path check wrote outside its directory')
    audio, rate, _ = render_ab(recovered.target, recovered.model, path=wav)
    require(set(audio) == {'A','B','D'} and all(np.isfinite(v).all() for v in audio.values()), 'Listening render failed')
    sf.write(work/'listening.wav', audio['A'], rate)
    app = make_window()
    try:
        require(Path(app.zoom_panel.template_path).is_file(), 'Default GUI template missing')
        require(app.zoom_panel.estimate()['active_slots'] == 0, 'Empty-bank preview failed')
        app.session = recovered; app.redraw(); app.update()
        app.figure.canvas.draw()
        app._sync_prep_config(PrepConfig(normalization='k_pink_band', level_db=-3.5))
        app.save_prep_defaults()
        tk_version = app.tk.call('info', 'patchlevel')
    finally:
        app.player.close(); app.destroy()
    app = make_window()
    try:
        require(app.read_prep().normalization == 'k_pink_band', 'Defaults reload failed')
        require(app.read_prep().level_db == -3.5, 'Defaults level reload failed')
        app.update_idletasks()
    finally:
        app.player.close(); app.destroy()
    metadata_path = application_root()/'MACOS_BUILD.json'
    return dict(success=True, version=__version__, platform=sys.platform, architecture=platform.machine(),
                frozen=bool(getattr(sys,'frozen',False)), python=platform.python_version(), tk=str(tk_version),
                k_modes=list(modes), wav_roundtrip=True, fir_training=True, project_roundtrip=True,
                bank_roundtrip=True, native_temp_export=True, user_symlink_rejected=True,
                gui_draw=True, defaults_reload=True, audio_render=True, afplay_found=bool(shutil.which('afplay')),
                audible_playback_test=False, pedal_test=False,
                build=json.loads(metadata_path.read_text()) if metadata_path.exists() else None)
