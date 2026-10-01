"""Portable regression tests for the native packaging contract (no OS claims)."""
import importlib.util
import json
from pathlib import Path
import plistlib
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit_macho import CPU, audit, packed_version, parse_macho, version
from compat_profile import locked_wheels, verify_environment
import build_macos


def binary(cpu=CPU['arm64'], minimum=12 << 16, endian='<', commands=None):
    commands = commands if commands is not None else [struct.pack(endian+'IIIIII', 0x32, 24, 1, minimum, 15 << 16, 0)]
    return struct.pack(endian+'IIIIIIII', 0xFEEDFACF, cpu, 0, 2, len(commands), sum(map(len, commands)), 0, 0) + b''.join(commands)


def fat(parts, wide=False, endian='>'):
    size = 32 if wide else 20
    offset = 8 + len(parts) * size
    table, payload = [], []
    for cpu, raw in parts:
        table.append(struct.pack(endian+('IIQQII' if wide else 'IIIII'), *([cpu, 0, offset, len(raw), 0] + ([0] if wide else []))))
        payload.append(raw);offset += len(raw)
    return struct.pack(endian+'II', 0xCAFEBABF if wide else 0xCAFEBABE, len(parts))+b''.join(table+payload)


class MachOTests(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(version('12'), (12, 0, 0))
        self.assertEqual(version('13.2.1'), (13, 2, 1))
        self.assertEqual(packed_version(0x000C0201), '12.2.1')
        for invalid in ('', '-1', '12.0.0.1', 'latest'):
            with self.assertRaises(ValueError): version(invalid)

    def test_non_macho(self):
        self.assertEqual(parse_macho(b'plain text'), [])

    def test_thin_endianness(self):
        for endian in ('<', '>'):
            self.assertEqual(parse_macho(binary(endian=endian))[0]['minimum_macos'], '12.0.0')

    def test_fat_and_fat64(self):
        for wide in (False, True):
            for endian in ('<', '>'):
                parts=[(CPU['arm64'],binary()),(CPU['x86_64'],binary(CPU['x86_64']))]
                self.assertEqual(len(parse_macho(fat(parts,wide,endian))),2)

    def test_old_version_command(self):
        cmd=struct.pack('<IIII',0x24,16,0x000A0F00,0x000F0000)
        self.assertEqual(parse_macho(binary(commands=[cmd]))[0]['minimum_macos'],'10.15.0')

    def test_missing_floor(self):
        self.assertIsNone(parse_macho(binary(commands=[]))[0]['minimum_macos'])

    def test_malformed(self):
        cases=[binary()[:9],binary()[:-1],binary(commands=[struct.pack('<II',0x32,4)]),
               struct.pack('>II',0xCAFEBABE,1000),
               fat([(CPU['arm64'],binary(CPU['x86_64']))]),
               binary(commands=[struct.pack('<IIIIII',0x32,24,2,12<<16,15<<16,0)])]
        for raw in cases:
            with self.subTest(raw=raw[:8]):
                with self.assertRaises(ValueError): parse_macho(raw)

    def make_app(self, root, raw=None, declared='12.0'):
        app=root/'HYBRID IR.app';(app/'Contents/MacOS').mkdir(parents=True)
        (app/'Contents/MacOS/HYBRID IR').write_bytes(binary() if raw is None else raw)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(LSMinimumSystemVersion=declared,CFBundleExecutable='HYBRID IR')))
        return app

    def test_bundle_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            result=audit(self.make_app(Path(temp)), '12.0','arm64')
            self.assertTrue(result['success']);self.assertFalse(result['runtime_test_on_target'])

    def test_bundle_rejects_false_minimum_or_architecture(self):
        for raw, declared in ((binary(minimum=14<<16),'12.0'),(binary(),'15.0'),
                              (binary(CPU['x86_64']),'12.0'),(binary(commands=[]),'12.0'),(b'not executable','12.0')):
            with self.subTest(declared=declared),tempfile.TemporaryDirectory() as temp:
                self.assertFalse(audit(self.make_app(Path(temp),raw,declared),'12.0','arm64')['success'])

    def test_minor_release_floor(self):
        with tempfile.TemporaryDirectory() as temp:
            app=self.make_app(Path(temp),binary(minimum=(12<<16)|(3<<8)))
            self.assertFalse(audit(app,'12.0','arm64')['success'])
            info=app/'Contents/Info.plist'
            data=plistlib.loads(info.read_bytes());data['LSMinimumSystemVersion']='12.3'
            info.write_bytes(plistlib.dumps(data))
            self.assertTrue(audit(app,'12.3','arm64')['success'])
        self.assertEqual(build_macos.COMPAT_MINIMUM,'12.3')

    def test_external_dylib_rejected(self):
        name=b'/opt/foreign/libtest.dylib\0';size=(24+len(name)+3)//4*4
        cmd=struct.pack('<IIIIII',0xC,size,24,0,0,0)+name+b'\0'*(size-24-len(name))
        versioncmd=struct.pack('<IIIIII',0x32,24,1,12<<16,15<<16,0)
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(audit(self.make_app(Path(temp),binary(commands=[versioncmd,cmd])),'12.0','arm64')['success'])

    def test_internal_and_external_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);app=self.make_app(root)
            link=app/'Contents/link'
            try: link.symlink_to('MacOS/HYBRID IR')
            except OSError: self.skipTest('Symlink creation unavailable')
            self.assertTrue(audit(app,'12.0','arm64')['success'])
            link.unlink();(root/'outside').write_text('outside');link.symlink_to(root/'outside')
            self.assertFalse(audit(app,'12.0','arm64')['success'])


class LockTests(unittest.TestCase):
    def test_committed_locks(self):
        for arch in ('arm64','x86_64'):
            records=locked_wheels(ROOT/'compat'/('requirements-'+arch+'.txt'),arch)
            self.assertEqual(len(records),22)
            self.assertEqual(records['numpy']['version'],'2.5.3')
            self.assertEqual(records['scipy']['version'],'1.18.1')
            self.assertNotIn('macosx_14_',records['numpy']['filename'])
            self.assertNotIn('macosx_14_',records['scipy']['filename'])

    def test_lock_failures(self):
        sha='0'*64
        valid='numpy @ https://files.pythonhosted.org/numpy-2.5.3-cp314-cp314-macosx_11_0_arm64.whl --hash=sha256:'+sha+'\n'
        cases=['',valid+valid,valid.replace('https:','http:'),valid.replace('_11_0_','_14_0_'),
               valid.replace('cp314-cp314','cp314-cp314t'),valid.replace('numpy @','scipy @'),
               valid.replace('cp314-cp314-macosx_11_0_arm64','py2-none-any')]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'req.txt'
            path.write_text(valid);self.assertIn('numpy',locked_wheels(path,'arm64'))
            for text in cases:
                path.write_text(text)
                with self.subTest(text=text),self.assertRaises(ValueError):locked_wheels(path,'arm64')

    def test_standard_remains_default(self):
        import inspect
        self.assertEqual(inspect.signature(build_macos.build).parameters['profile'].default,'standard')
        spec=(ROOT/'HYBRIDIR.spec').read_text()
        self.assertIn("'LSMinimumSystemVersion':metadata['minimum_macos']",spec)

    def test_wrong_python_refused(self):
        with patch('compat_profile.platform.python_version',return_value='3.14.7'):
            with self.assertRaises(ValueError):verify_environment(ROOT.parent.parent,'arm64')


if __name__=='__main__':unittest.main()
