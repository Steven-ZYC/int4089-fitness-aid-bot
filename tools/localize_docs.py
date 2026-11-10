"""Local documentation migration helpers; source snapshots are immutable."""
from pathlib import Path
import re
import textwrap

FENCE=re.compile(r'(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*(?:\n|$)')

def source(name):
    p=Path(name)
    return p.with_name(p.stem+'_zh_cn'+p.suffix).read_text(encoding='utf-8-sig')

def blocks(name):
    return [m.group(0) for m in FENCE.finditer(source(name))]

def preview(*names):
    for name in names:
        i=iter(range(1000))
        print('\nFILE:',name)
        print(FENCE.sub(lambda m:f'@@{next(i)}@@\n',source(name)))

def publish(name,text):
    text=textwrap.dedent(text).lstrip('\n')
    for i,block in enumerate(blocks(name)):
        token=f'@@{i}@@'
        if text.count(token)!=1:
            raise ValueError(f'{name}: missing/duplicate {token}')
        text=text.replace(token,block.rstrip('\n'))
    if re.search(r'@@\d+@@',text):raise ValueError(name+' unknown code placeholder')
    Path(name).write_text(text.rstrip()+'\n',encoding='utf-8')
