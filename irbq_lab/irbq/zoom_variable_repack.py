"""Experimental, hash-gated repacking of SDK HVB2 ZDLs only.

Requires the bank at the .const tail. Does not support arbitrary Zoom ELF.
Address fields/instruction immediates are relocated, never DSP operations.
"""
import hashlib
import struct
from .zoom_variable_bank import validate


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def put(data, offset, value):
    if not 0 <= value <= 0xffffffff:
        raise ValueError('ELF32 overflow')
    struct.pack_into('<I', data, offset, value)


def layout(raw):
    if len(raw)<128 or raw[:8]!=b'\0\0\0\0SIZE' or u32(raw,12)!=56 or u32(raw,16)!=len(raw)-76:
        raise ValueError('Unsupported ZDL wrapper')
    elf=raw[76:]
    if elf[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH',elf,16)!=(3,140):
        raise ValueError('Unsupported ELF ABI')
    po,so=u32(elf,28),u32(elf,32)
    pe,pn,se,sn,strings=struct.unpack_from('<5H',elf,42)
    if pe!=32 or se!=40 or pn!=4 or sn!=13 or strings!=12 or so+sn*40>len(elf) or po+pn*32>len(elf):
        raise ValueError('Unsupported ELF tables')
    sections=[list(struct.unpack_from('<10I',elf,so+40*i)) for i in range(sn)]
    names=sections[strings]
    text=elf[names[4]:names[4]+names[5]]
    result={}
    for i,s in enumerate(sections):
        if s[1]==8 or s[4]+s[5]>len(elf):raise ValueError('Unsupported section')
        name=text[s[0]:text.index(0,s[0])].decode('ascii')
        result[name]=(i,s)
    return elf,po,so,sections,result


def _repack(raw, bank, *, expected_sha256, bank_validate, magic, extent):
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('Unknown variable-bank template')
    report=bank_validate(bank)
    elf,po,so,sections,names=layout(raw)
    ci,c=names['.const'];fi,far=names['.fardata']
    const=elf[c[4]:c[4]+c[5]]
    if const.count(magic)!=1 or const.count(extent)!=1:
        raise ValueError('Ambiguous bank/extent anchors')
    start=c[4]+const.index(magic);meta=c[4]+const.index(extent)
    old_size=u32(elf,start+8);end=c[4]+c[5]
    bank_validate(elf[start:start+old_size])
    if u32(elf,meta+4)!=old_size or not (meta+12<=start and 0<=end-start-old_size<8):
        raise ValueError('Bank is not the final const object')
    if any(elf[start+old_size:end]) or far[4]!=end or far[3]!=c[3]+c[5]:
        raise ValueError('Unexpected section padding/layout')
    padded=bank+b'\0'*((-len(bank))%8)
    delta=len(padded)-(end-start)
    bank_va=c[3]+start-c[4]

    def file_offset(value):
        return value+delta if value>=end else value

    def address(value):
        if bank_va+64<=value<bank_va+old_size:
            raise ValueError('Template embeds a bank-payload address')
        return value+delta if far[3]<=value<far[3]+far[5] else value

    new=bytearray(elf[:start]+padded+elf[end:])
    put(new,meta+4,len(bank))
    put(new,meta+8,struct.unpack('<I',struct.pack('<f',1/(report['entry_count']-1)))[0])
    put(new,28,file_offset(po));put(new,32,file_offset(so))
    for index,s in enumerate(sections):
        updated=s.copy()
        if index==ci:updated[5]+=delta
        elif s[4]>=end:updated[4]+=delta
        if index==fi:updated[3]+=delta
        struct.pack_into('<10I',new,file_offset(so)+40*index,*updated)
    for i in range(4):
        p=list(struct.unpack_from('<8I',elf,po+32*i))
        if p[0]==1 and p[2]==c[3]:p[4]+=delta;p[5]+=delta
        elif p[0]==1 and p[2]==far[3]:p[1]+=delta;p[2]+=delta;p[3]+=delta
        elif p[1]>=end:p[1]+=delta
        struct.pack_into('<8I',new,file_offset(po)+32*i,*p)
    _,syms=names['.dynsym'];_,strings=names['.dynstr']
    symbols=[];named={}
    for offset in range(syms[4],syms[4]+syms[5],16):
        ni,value,size,info,other,section=struct.unpack_from('<IIIBBH',elf,offset)
        symbol_name=elf[strings[4]+ni:elf.index(0,strings[4]+ni)].decode('ascii')
        symbols.append((value,section))
        if symbol_name:named[symbol_name]=(value,size,section)
        put(new,file_offset(offset)+4,address(value) if section in (ci,fi) else value)
    _,dynamic=names['.dynamic']
    for offset in range(dynamic[4],dynamic[4]+dynamic[5],8):
        tag,value=struct.unpack_from('<II',elf,offset)
        if tag in (4,5,6,7,23):put(new,file_offset(offset)+4,file_offset(value))

    def locate(value):
        for s in sections:
            if s[2]&2 and s[3]<=value and value+4<=s[3]+s[5]:return s[4]+value-s[3]
        raise ValueError('Relocation outside allocated sections')

    relocations=0
    for s in sections:
        if s[1]==9:raise ValueError('Implicit relocations not supported')
        if s[1]!=4:continue
        if s[5]%12:raise ValueError('Invalid RELA size')
        for offset in range(s[4],s[4]+s[5],12):
            target,info,addend=struct.unpack_from('<IIi',elf,offset)
            kind=info&255;index=info>>8
            if addend or kind not in (1,9,10) or not 0<index<len(symbols):
                raise ValueError('Unsupported relocation')
            value,section=symbols[index]
            value=address(value) if section in (ci,fi) else value
            put(new,file_offset(offset),address(target))
            at=file_offset(locate(target))
            if kind==1:put(new,at,value)
            else:
                word=u32(new,at)
                put(new,at,(word&~(0xffff<<7))|(((value>>(16 if kind==10 else 0))&0xffff)<<7))
            relocations+=1
    # Some stock-style image-info slots lack RELA entries; relocate explicitly.
    info_va,info_size,_=named['effectTypeImageInfo']
    info_at=locate(info_va)
    for i in range(min(9,(info_size-0x24)//16)):
        at=info_at+0x30+i*16
        value=u32(elf,at)
        if value:put(new,file_offset(at),address(value))
    desc_va,_,_=named['SonicStomp'];desc=locate(desc_va)
    # Selector positions follow descriptor names, not a fixed page order.
    selectors=[]
    for index in range(2,11):
        label=elf[desc+48*index:desc+48*index+12].split(b'\0')[0]
        if label in (b'IR-L',b'IR-R'):selectors.append(index)
    if len(selectors)!=2:raise ValueError('Expected two IR selector descriptors')
    for index in selectors:put(new,desc+48*index+12,report['entry_count']-1)
    result=bytearray(raw[:76])+new
    put(result,16,len(new))
    layout(result)
    return bytes(result), dict(report,relocations=relocations,const_delta=delta,
                               const_bytes=c[5]+delta,zdl_bytes=len(result),hardware_validated=False)


def repack(raw, bank, *, expected_sha256):
    return _repack(raw, bank, expected_sha256=expected_sha256, bank_validate=validate,
                   magic=b'HVB2', extent=b'HBM2')


def repack_roles(raw, bank, *, expected_sha256):
    from .zoom_rbj_bank import validate as validate_roles
    return _repack(raw, bank, expected_sha256=expected_sha256, bank_validate=validate_roles,
                   magic=b'HVB4', extent=b'HBM4')
