"""Desktop engine wrapper -> real global hotkey -> CUDA -> native text field."""
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
import replay_integration
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences,Settings

def run():
    config=root/'.work/desktop-external/settings.json'
    Preferences(config).save(Settings(activation='toggle',shortcuts={'toggle':0x81,'retry':0x82,'cancel':0x83,'quit':0x84,'save':0x85}))
    backend=worker.build_backend(config,root/'models')
    original=replay_integration.app.Dictation
    original_send=worker.send
    events=[]
    replay_integration.app.Dictation=lambda args:backend
    worker.send=lambda kind,**data:events.append({'event':kind,**data})
    try:
        result=replay_integration.run()
        delivered=[event for event in events if event['event']=='result']
        assert delivered and delivered[-1]['delivered'] and delivered[-1]['destination']=='external'
        result['desktop_wrapper_external_delivery_verified']=True
        result['delivery_metrics']=delivered[-1]['metrics']
        return result
    finally:
        replay_integration.app.Dictation=original
        worker.send=original_send

if __name__=='__main__':
    result=run()
    (root/'results/desktop-external-0.3.0.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
