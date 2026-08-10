#!/usr/bin/env python3
"""Read-only analyzer for the Ricoh GXR debug/service system in firmware 1.51.

It never modifies firmware. It parses Ricoh section headers, the fixed 25-command
system-shell table, the 40-command service-script table, and the 41-entry low-level
module registry from the body main program (ilaunch3).
"""
from __future__ import annotations
import argparse, csv, json, struct, tempfile, zipfile
from pathlib import Path

HEADER=0x200

def cstr(b:bytes)->str:
    return b.split(b'\0',1)[0].decode('ascii','replace')

def sections(d:bytes):
    out=[]
    for i,off in enumerate(range(0x20,0x160,20)):
        rec=struct.unpack_from('>IIIII',d,off)
        if not any(rec): break
        src,va,size,bss,bssz=rec
        if HEADER+src+size>len(d): break
        out.append({'index':i,'file_start':HEADER+src,'file_end':HEADER+src+size,
                    'va_start':va,'va_end':va+size,'bss_start':bss,'bss_size':bssz})
    return out

def valid_va(x,secs): return any(s['va_start']<=x<s['va_end'] for s in secs)
def va_to_file(x,secs):
    for s in secs:
        if s['va_start']<=x<s['va_end']:
            return s['file_start']+(x-s['va_start'])
    return None

def scan_system_shell(d,secs):
    best=[]
    for start in range(0,len(d)-0x100,4):
        recs=[]; pos=start
        while pos+0x50<=len(d):
            fn=struct.unpack_from('>I',d,pos)[0]
            name=cstr(d[pos+4:pos+12])
            help_text=cstr(d[pos+12:pos+0x50].lstrip(b'\0'))
            good=(valid_va(fn,secs) and 1<=len(name)<=8 and
                  all(ch.isalnum() or ch in '_-?' for ch in name) and
                  len(help_text)>=4 and all(32<=ord(ch)<127 for ch in help_text))
            if not good: break
            recs.append({'record_offset':pos,'name':name,'function_va':fn,
                         'function_file_offset':va_to_file(fn,secs),'help':help_text})
            pos+=0x50
        if len(recs)>len(best): best=recs
    return best

def scan_module_registry(d):
    # Known by structure: name[32], init VA, fini VA, beginning at 0x76060 in 1.51 body.
    out=[]
    for off in range(0x76060,0x766e0,0x28):
        name=cstr(d[off:off+32]); init,fini=struct.unpack_from('>II',d,off+32)
        if name:
            out.append({'record_offset':off,'name':name,'init_va':init,'fini_va':fini})
    return out

def scan_domains(d):
    out=[]
    for off in range(0x766f0,0x76830,0x20):
        name=cstr(d[off:off+16]); ident,flags,p1,p2=struct.unpack_from('>IIII',d,off+16)
        if name: out.append({'record_offset':off,'name':name,'id':ident,'flags':flags,'callback1':p1,'callback2':p2})
    return out

def scan_script_commands(d):
    # Known structure: name[16], function VA, eight metadata bytes. Starts at 0x80f80.
    out=[]
    off=0x80f80
    while off+0x1c<=len(d):
        name=cstr(d[off:off+16])
        if not name: break
        fn=struct.unpack_from('>I',d,off+16)[0]
        meta=list(d[off+20:off+28])
        out.append({'record_offset':off,'name':name,'function_va':fn,'arg_metadata':meta})
        off+=0x1c
        if name=='repeat2': break
    return out

def all_offsets(d,needle:bytes):
    out=[]; p=0
    while True:
        p=d.find(needle,p)
        if p<0:return out
        out.append(p);p+=1

def locate_body(root:Path)->Path:
    hits=list(root.rglob('ilaunch3'))
    if not hits: raise FileNotFoundError('ilaunch3 not found')
    return hits[0]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('input',type=Path,help='official GXR ZIP, extracted folder, or ilaunch3')
    ap.add_argument('--json',type=Path,default=Path('gxr_debug_report.json'))
    ap.add_argument('--csv-dir',type=Path)
    a=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='gxrdbg_') as td:
        if a.input.is_file() and zipfile.is_zipfile(a.input):
            with zipfile.ZipFile(a.input) as z:z.extractall(td)
            body=locate_body(Path(td))
        elif a.input.is_dir(): body=locate_body(a.input)
        else: body=a.input
        d=body.read_bytes(); secs=sections(d)
        report={
          'file':str(body),'size':len(d),'sections':secs,
          'system_shell_commands':scan_system_shell(d,secs),
          'service_script_commands':scan_script_commands(d),
          'low_level_modules':scan_module_registry(d),
          'debug_domains':scan_domains(d),
          'trigger_files':{
             s:all_offsets(d,s.encode()) for s in [
               '/ATA1/DBGMODE.key','/ATA1/INCOPY.KEY','/ATA1/COMMAND.NS1',
               '/ATA1/SCRIPT.MG1','/CONFIG.TST','/CONFIG.BAK','/SCINST.TST']},
          'notes':[
            'Read-only static analysis; no firmware bytes were modified.',
            'Presence of a command or trigger string does not prove a safe public entry procedure.',
            'ROM erase/write-test, memory edit/fill/copy, arbitrary function execution and adjustment restore are destructive-capable.'
          ]}
        a.json.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if a.csv_dir:
            a.csv_dir.mkdir(parents=True,exist_ok=True)
            for key,name in [('system_shell_commands','system_shell_commands.csv'),('service_script_commands','service_script_commands.csv'),('low_level_modules','low_level_modules.csv'),('debug_domains','debug_domains.csv')]:
                rows=report[key]
                with (a.csv_dir/name).open('w',newline='',encoding='utf-8-sig') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
    print(a.json)
if __name__=='__main__': main()
