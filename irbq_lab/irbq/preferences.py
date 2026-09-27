"""User interface preferences, separate from portable DSP projects."""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from pathlib import Path
import json
import os
import tempfile

@dataclass
class Preferences:
    language: str = 'en'
    theme: str = 'dark'
    edit_enabled: bool = False
    show_bands: bool = False
    show_bq_sum: bool = False
    def validate(self):
        if self.language not in ('ru','en'): self.language='en'
        if self.theme not in ('light','dark'): self.theme='dark'
        for key in ('edit_enabled','show_bands','show_bq_sum'):
            if not isinstance(getattr(self,key),bool): setattr(self,key,False)
        return self

def settings_path():
    override=os.environ.get('IRBQ_SETTINGS_PATH')
    if override: return Path(override).expanduser()
    if os.name=='nt':
        base=Path(os.environ.get('APPDATA',Path.home()/'AppData'/'Roaming'))
    else:
        base=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    return base/'IRBQ_Lab'/'settings.json'

def load_preferences(path=None):
    try:
        data=json.loads(Path(path or settings_path()).read_text(encoding='utf-8'))
        if not isinstance(data,dict): return Preferences()
        return Preferences(**{k:v for k,v in data.items() if k in {f.name for f in fields(Preferences)}}).validate()
    except (OSError, ValueError, TypeError):
        return Preferences()

def save_preferences(prefs, path=None):
    """Atomic replace; the caller can report a read-only-profile error without losing the project."""
    dest=Path(path or settings_path());dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=dest.parent,prefix='.settings-',suffix='.json',delete=False) as f:
            tmp=Path(f.name)
            json.dump(asdict(prefs.validate()),f,indent=2,ensure_ascii=False);f.write('\n')
        os.replace(tmp,dest)
    finally:
        if tmp and tmp.exists():tmp.unlink()
