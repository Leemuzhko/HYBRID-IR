"""Shared build and packaging pipeline for minimal SDK effects."""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildResult:
    effect_dir: Path
    object_path: Path
    zdl_path: Path
    metadata_path: Path | None


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def _load_build_modules(repo_root: Path):
    build_dir = repo_root / "build"
    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))

    from linker import LinkerConfig, link, params_from_manifest
    from toolchain import find_ti_root, ti_executable
    from zdl_smoke import validate_object, validate_zdl

    return (
        LinkerConfig,
        link,
        params_from_manifest,
        find_ti_root,
        ti_executable,
        validate_object,
        validate_zdl,
    )


def load_manifest(effect_dir: Path) -> dict:
    path = effect_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("sdk_profile") != "minimal-v1":
        raise ValueError(
            f"{path} is not a minimal SDK manifest "
            '(expected "sdk_profile": "minimal-v1")'
        )
    return manifest


def output_basename(manifest: dict) -> str:
    return str(manifest.get("output_basename", manifest["effect_name"]))


def make_extended_header(config: dict) -> bytes:
    """Create a metadata record without borrowing a stock effect payload."""
    kind = str(config.get("type", "")).upper()
    if kind != "CABI":
        raise ValueError(f"unsupported extended header type: {kind!r}")

    lines = list(config.get("lines", []))
    if len(lines) != 3:
        raise ValueError("CABI extended header requires exactly three lines")

    payload = bytearray(256)
    payload[0:4] = b"CABI"
    struct.pack_into("<I", payload, 4, 248)
    struct.pack_into("<I", payload, 8, int(config["id"]))
    for offset, value in zip((0x0C, 0x14, 0x1C), lines):
        encoded = str(value).encode("ascii")
        if len(encoded) > 8:
            raise ValueError(f"CABI line {value!r} exceeds 8 ASCII bytes")
        payload[offset : offset + 8] = encoded.ljust(8, b"\0")
    return bytes(payload)


def apply_extended_header(zdl_path: Path, config: dict, repo_root: Path) -> None:
    build_dir = repo_root / "build"
    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))
    from zdl import HEADER_SIZE_TYPICAL, Zdl

    zdl = Zdl.load(zdl_path)
    payload = make_extended_header(config)
    zdl.extra_header_payload = payload
    zdl.header_size = HEADER_SIZE_TYPICAL + len(payload)
    zdl.save(zdl_path)


def package_effect(
    effect_dir: Path,
    zdl_path: Path,
    output_dir: Path,
) -> Path | None:
    manifest = load_manifest(effect_dir)
    ui = dict(manifest.get("ui", {}))
    basename = output_basename(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    destination = output_dir / f"{basename}.ZDL"
    if zdl_path.resolve() != destination.resolve():
        shutil.copy2(zdl_path, destination)

    metadata_source = effect_dir / f"{basename}.json"
    metadata_destination: Path | None = None
    if metadata_source.is_file():
        metadata_destination = output_dir / metadata_source.name
        if metadata_source.resolve() != metadata_destination.resolve():
            shutil.copy2(metadata_source, metadata_destination)
    return metadata_destination


def build_effect(
    effect_dir: Path,
    repo_root: Path,
    output_dir: Path | None = None,
) -> BuildResult:
    _configure_console()
    effect_dir = effect_dir.resolve()
    repo_root = repo_root.resolve()
    manifest = load_manifest(effect_dir)
    ui = dict(manifest.get("ui", {}))

    (
        LinkerConfig,
        link,
        params_from_manifest,
        find_ti_root,
        ti_executable,
        validate_object,
        validate_zdl,
    ) = _load_build_modules(repo_root)

    effect_name = str(manifest["effect_name"])
    basename = output_basename(manifest)
    source_name = str(manifest.get("source_file", f"{effect_name.lower()}.c"))
    source_path = effect_dir / source_name
    if not source_path.is_file():
        raise FileNotFoundError(f"C source not found: {source_path}")

    ti_root = find_ti_root(repo_root)
    cl6x = ti_executable(ti_root, "cl6x")
    object_path = effect_dir / f"{Path(source_name).stem}.obj"
    if output_dir is None:
        output_dir = repo_root / "dist" / f"{basename.lower()}-folder"
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    zdl_path = output_dir / f"{basename}.ZDL"

    cflags = [
        "--c99",
        "--opt_level=2",
    ]
    # Opt-in only: preserve compiler behavior for every existing SDK client.
    if "opt_for_space" in manifest:
        space = manifest["opt_for_space"]
        if type(space) is not int or not 0 <= space <= 3:
            raise ValueError("opt_for_space must be an integer in 0..3")
        cflags.append(f"--opt_for_space={space}")
    materialize_saved_params = bool(
        manifest.get("materialize_saved_params", False)
    )
    if materialize_saved_params:
        param_count = len(manifest["params"])
        materialize_max = 10 if bool(
            manifest.get("allow_experimental_fourth_page", False)
        ) else 9
        if param_count < 1 or param_count > materialize_max:
            raise ValueError(
                "materialize_saved_params requires 1..9 user parameters "
                "(or 10 with allow_experimental_fourth_page)"
            )
        init_function = (
            f"{manifest.get('audio_func_name', f'Fx_FLT_{effect_name}')}_init"
        )
        cflags.extend(
            [
                f"--define=ZOOM_MATERIALIZE_INIT_FUNCTION={init_function}",
                f"--define=ZOOM_MATERIALIZE_PARAM_COUNT={param_count}",
                "--preinclude=zoom_materialize_init.h",
            ]
        )
    interrupt_threshold = manifest.get("interrupt_threshold")
    if interrupt_threshold is not None:
        cflags.append(f"--interrupt_threshold={int(interrupt_threshold)}")
    cflags.extend(
        [
            "-mv6740",
            "--abi=eabi",
            "--mem_model:data=far",
            f"--include_path={ti_root / 'include'}",
            f"--include_path={repo_root / 'sdk' / 'include'}",
        ]
    )

    label = effect_name.lower()
    print(f"[{label}] TI root: {ti_root}")
    print(f"[{label}] compiling {source_path}")
    subprocess.run(
        [
            str(cl6x),
            *cflags,
            "-c",
            str(source_path),
            f"--output_file={object_path}",
        ],
        cwd=effect_dir,
        check=True,
    )
    materialize_externals = frozenset(
        {
            "__c6xabi_call_stub",
            "__c6xabi_pop_rts",
            "__c6xabi_push_rts",
        }
        if materialize_saved_params
        else ()
    )
    validate_object(
        object_path,
        allow_text=(
            bool(manifest.get("allow_text_section", False))
            or materialize_saved_params
        ),
        expected_external_symbols=materialize_externals,
        expected_local_relocation_symbols=frozenset(
            str(name)
            for name in manifest.get(
                "expected_local_relocation_symbols",
                [],
            )
        ),
        allow_expected_external_relocations=materialize_saved_params,
    )

    screen_image = None
    screen = ui.get("screen")
    if screen == "bottom-label":
        from screen_image import make_bottom_label_screen
        screen_image = make_bottom_label_screen(effect_name)
    elif screen == "amp-ui-test":
        from screen_image import make_ui_amp_screen
        screen_image = make_ui_amp_screen()
    elif isinstance(screen, str) and screen:
        screen_path = effect_dir / screen
        screen_image = screen_path.read_bytes()

    positions = ui.get("positions")
    knob_positions = (
        [tuple(int(v) for v in item) for item in positions]
        if positions is not None
        else None
    )
    control_words = ui.get("control_info_words")
    control_info_bytes = (
        struct.pack("<6I", *(int(v) for v in control_words))
        if control_words is not None
        else None
    )
    control_words_by_slot = ui.get("control_info_words_by_slot")
    control_info_bytes_by_slot = None
    if control_words_by_slot is not None:
        control_info_bytes_by_slot = [
            struct.pack("<6I", *(int(v) for v in words))
            for words in control_words_by_slot
        ]
    custom_sprites = None
    raw_custom_sprites = ui.get("custom_sprites")
    if raw_custom_sprites is not None:
        custom_sprites = []
        for index, raw in enumerate(raw_custom_sprites):
            if not isinstance(raw, dict):
                raise ValueError(
                    f"ui.custom_sprites[{index}] must be an object"
                )
            data_name = raw.get("data") or raw.get("data_file")
            if not data_name:
                raise ValueError(
                    f"ui.custom_sprites[{index}] needs a data/data_file path"
                )
            data_path = effect_dir / str(data_name)
            if not data_path.is_file():
                raise FileNotFoundError(
                    f"custom sprite data not found: {data_path}"
                )
            custom_sprites.append(
                {
                    "slot": int(raw["slot"]),
                    "width": int(raw["width"]),
                    "height": int(raw["height"]),
                    "frame_count": int(raw["frame_count"]),
                    "direction": int(raw.get("direction", 0)),
                    "renderer_style": int(raw.get("renderer_style", 12)),
                    "data": data_path.read_bytes(),
                }
            )
    header_words = ui.get("header_words")
    image_header_words = (
        tuple(int(v) for v in header_words)
        if header_words is not None
        else None
    )

    link(
        LinkerConfig(
            effect_name=effect_name,
            audio_func_name=manifest.get("audio_func_name"),
            gid=int(manifest["gid"]),
            fxid=int(manifest["fxid"]),
            params=params_from_manifest(manifest["params"]),
            obj_path=object_path,
            output_path=zdl_path,
            fxid_version=str(manifest.get("fxid_version", "1.00")).encode("ascii"),
            flags_byte=int(manifest.get("flags_byte", 1)),
            knob_type=int(manifest.get("knob_type", 0)),
            screen_image=screen_image,
            knob_positions=knob_positions,
            control_info_bytes=control_info_bytes,
            control_info_bytes_by_slot=control_info_bytes_by_slot,
            custom_sprites=custom_sprites,
            image_info_knob_count=ui.get("image_info_knob_count"),
            image_info_header_words=image_header_words,
            audio_nop=bool(manifest.get("audio_nop", False)),
            use_object_edit_handlers=False,
            synthesize_linesel_edit_handlers=bool(
                manifest.get("synthesize_linesel_edit_handlers", False)
            ),
            synth_edit_start_index=int(
                manifest.get("synth_edit_start_index", 2)
            ),
            synth_handler_mode=str(
                manifest.get("synth_handler_mode", "full")
            ),
            synth_handler_mode_indices=tuple(
                int(v) for v in manifest.get("synth_handler_mode_indices", [])
            ),
            use_object_init_handler=bool(
                manifest.get("use_object_init_handler", False)
            ) or materialize_saved_params,
            allow_experimental_fourth_page=bool(
                manifest.get("allow_experimental_fourth_page", False)
            ),
            disable_stock_handlers=bool(
                manifest.get("disable_stock_handlers", False)
            ),
        )
    )
    extended_header = manifest.get("extended_header")
    if extended_header is not None:
        apply_extended_header(zdl_path, dict(extended_header), repo_root)
    validate_zdl(
        zdl_path,
        max_fardata_size=int(manifest.get("smoke_max_fardata_bytes", 24)),
    )
    metadata_path = package_effect(effect_dir, zdl_path, output_dir)
    print(f"[{label}] Zoom Effect Manager folder: {output_dir}")
    return BuildResult(effect_dir, object_path, zdl_path, metadata_path)
