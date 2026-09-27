"""Build reserved IDs from ZEM original_effects (stock and bundled Other effects)."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    records=[]
    for path in sorted(args.source.rglob('*')):
        if path.suffix.lower()!='.zdl':continue
        raw=path.read_bytes()
        if len(raw)<80 or raw[:8]!=b'\0\0\0\0SIZE' or raw[20:24]!=b'INFO':
            raise ValueError(f'Invalid ZDL: {path.name}')
        records.append(dict(gid=raw[60],fxid=struct.unpack_from('<H',raw,64)[0],
                            name=path.stem,source=path.relative_to(args.source).as_posix(),
                            sha256=hashlib.sha256(raw).hexdigest()))
    if not records:raise ValueError('No original effects found')
    payload=dict(schema='hybridir-reserved-ids/1',
                 scope='ZEM original_effects snapshot, including stock, cross-model and bundled Other effects (RainSel, RTFM, Div0). Not a live pedal inventory or guarantee of all future IDs.',
                 entries=records)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(payload,stream,indent=2,ensure_ascii=True)
    print(f'{len(records)} sources, {len({(r["gid"],r["fxid"]) for r in records})} reserved identities')

if __name__=='__main__':main()
