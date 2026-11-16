from pathlib import Path
import importlib.metadata
import json
import shutil
import sys

target=Path(sys.argv[1])/'third-party-licenses'
target.mkdir(parents=True,exist_ok=True)
summary=[]
for name in ('customtkinter','darkdetect','pillow','psutil','packaging','pyinstaller'):
    distribution=importlib.metadata.distribution(name)
    copied=[]
    for item in distribution.files or ():
        if ('license' in item.name.casefold() or item.name.casefold().startswith(('copying','notice'))) and item.suffix.lower() not in ('.py','.pyc'):
            source=Path(distribution.locate_file(item))
            if source.is_file():
                relative=Path(*[part for part in item.parts if part not in ('..','.','/','\\')])
                destination=target/name/relative
                if not destination.resolve().is_relative_to(target.resolve()): raise RuntimeError('Invalid license metadata path')
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,destination)
                copied.append(str(destination.relative_to(target)))
    summary.append({'name':name,'version':distribution.version,
        'metadata_license':distribution.metadata.get('License-Expression',distribution.metadata.get('License','See upstream notices')),
        'files':copied})
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file(): shutil.copyfile(python_license,target/'Python-LICENSE.txt')
for base in (Path(sys.base_prefix)/'tcl',Path(sys.base_prefix)/'Lib'):
    if base.is_dir():
        for source in base.glob('**/license.terms'):
            destination=target/('Tcl-Tk-'+source.parent.name+'-license.terms')
            shutil.copyfile(source,destination)
(target/'dependencies.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
extra=Path(__file__).resolve().parents[1]/'assets/licenses'
if extra.is_dir(): shutil.copytree(extra,target/'additional',dirs_exist_ok=True)
print('Collected third-party notices in',target)
