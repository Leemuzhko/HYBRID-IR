"""Static smoke checks shared by minimal SDK examples."""

from __future__ import annotations

import struct
from pathlib import Path

from linker import ObjFile
from zdl import Zdl


def _section_map(elf: bytes) -> dict[str, tuple[int, ...]]:
    shoff = struct.unpack_from("<I", elf, 0x20)[0]
    shentsize = struct.unpack_from("<H", elf, 0x2E)[0]
    shnum = struct.unpack_from("<H", elf, 0x30)[0]
    shstrndx = struct.unpack_from("<H", elf, 0x32)[0]
    headers = [
        struct.unpack_from("<10I", elf, shoff + i * shentsize)
        for i in range(shnum)
    ]
    names_header = headers[shstrndx]
    names = elf[names_header[4] : names_header[4] + names_header[5]]
    result: dict[str, tuple[int, ...]] = {}
    for header in headers:
        end = names.find(b"\0", header[0])
        name = names[header[0] : end].decode("ascii", "replace") if end >= 0 else ""
        result[name] = header
    return result


def validate_object(
    obj_path: Path,
    *,
    allow_text: bool = False,
    expected_external_symbols: frozenset[str] = frozenset(),
    expected_local_relocation_symbols: frozenset[str] = frozenset(),
    allow_expected_external_relocations: bool = False,
) -> None:
    obj = ObjFile(obj_path)
    externals = sorted(
        symbol["name"]
        for symbol in obj.symbols
        if symbol["shndx"] == 0 and symbol["name"]
    )
    forbidden = []
    for section in obj.sections:
        if section["size"] and (
            section["name"] == ".bss"
            or section["name"] == ".far"
            or section["name"].startswith(".far:")
            or (section["name"] == ".text" and not allow_text)
        ):
            forbidden.append(f"{section['name']}={section['size']}")
    loadable_section_names = {".audio", ".text", ".const", ".fardata"}
    loadable_relocations = [
        entry
        for section_index, entries in obj.relocs.items()
        if obj.sections[section_index]["name"] in loadable_section_names
        or obj.sections[section_index]["name"].startswith(".const:")
        for entry in entries
    ]
    relocation_count = len(loadable_relocations)
    actual_external_symbols = frozenset(externals)
    if actual_external_symbols != expected_external_symbols:
        raise RuntimeError(
            "external-symbol contract mismatch: "
            f"expected={sorted(expected_external_symbols)}, "
            f"actual={externals}"
        )
    if forbidden:
        raise RuntimeError(f"forbidden minimal-SDK object sections: {forbidden}")
    allow_known_relocations = (
        allow_expected_external_relocations
        or bool(expected_local_relocation_symbols)
    )
    if relocation_count and not allow_known_relocations:
        raise RuntimeError(
            f"minimal SDK object is not self-contained: "
            f"{relocation_count} relocation(s)"
        )
    if relocation_count:
        relocation_symbols = {
            obj.symbols[entry["sym_idx"]]["name"]
            for entry in loadable_relocations
        }
        expected_relocation_symbols = (
            expected_external_symbols | expected_local_relocation_symbols
        )
        unexpected_relocation_symbols = relocation_symbols - expected_relocation_symbols
        if unexpected_relocation_symbols:
            raise RuntimeError(
                "unexpected relocation symbols: "
                f"{sorted(unexpected_relocation_symbols)}"
            )


def validate_zdl(path: Path, max_fardata_size: int = 24) -> None:
    if len(path.stem) > 8:
        raise RuntimeError("ZDL basename exceeds the pedal's 8-character limit")

    zdl = Zdl.load(path)
    elf = zdl.elf
    if struct.unpack_from("<H", elf, 0x10)[0] != 3:
        raise RuntimeError("embedded ELF is not ET_DYN")
    if struct.unpack_from("<H", elf, 0x12)[0] != 140:
        raise RuntimeError("embedded ELF is not TI C6000")

    phoff = struct.unpack_from("<I", elf, 0x1C)[0]
    phentsize = struct.unpack_from("<H", elf, 0x2A)[0]
    phnum = struct.unpack_from("<H", elf, 0x2C)[0]
    for index in range(phnum):
        header = struct.unpack_from("<8I", elf, phoff + index * phentsize)
        p_type, _, _, _, filesz, memsz, _, _ = header
        if p_type == 1 and filesz != memsz:
            raise RuntimeError(
                f"PT_LOAD[{index}] has filesz={filesz}, memsz={memsz}"
            )

    sections = _section_map(elf)
    for name in (".bss", ".far"):
        section = sections.get(name)
        if section and section[5]:
            raise RuntimeError(f"unsafe output section {name}={section[5]}")
    fardata_size = sections.get(".fardata", (0, 0, 0, 0, 0, 0))[5]
    if fardata_size > max_fardata_size:
        raise RuntimeError(
            f".fardata is larger than the configured smoke limit "
            f"({fardata_size} > {max_fardata_size})"
        )

    print("[sdk] smoke check")
    print(f"  wrapper:   OK ({path.stat().st_size} bytes)")
    print(f"  ELF:       ET_DYN / TI C6000 ({len(elf)} bytes)")
    print("  PT_LOAD:   memsz == filesz")
    print(f"  .fardata:  {fardata_size} bytes")
    print(f"  filename:  {len(path.stem)} + 4 characters (pedal-safe)")
