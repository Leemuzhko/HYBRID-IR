"""Process-lifetime Windows mutex shared by launch, update and uninstall."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path


@contextmanager
def installation_lock(root, *, allow_pending=False):
    if os.name != 'nt':
        raise OSError('Installation lifecycle operations require Windows')
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    identity = str(Path(root).resolve()).casefold().encode('utf-8')
    name = 'Local\\HYBRIDIR_' + hashlib.sha256(identity).hexdigest()
    handle = kernel.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    try:
        if error == 183:
            raise ValueError('HYBRID IR is running or another install/uninstall is active. Close it and retry.')
        journal = Path(root).parent / (Path(root).name + '.update.json')
        if journal.exists() and not allow_pending:
            raise ValueError('An interrupted update needs recovery. See ' + str(journal))
        yield
    finally:
        kernel.CloseHandle(handle)
