"""Explicit, loopback-only optional AI; conservative rejection is intentional."""
import json
import re
import urllib.request
from ..text_processing import LITERALS, resolve_spoken_corrections, semantic_tokens

def local_request(provider,port,path,payload=None,timeout=2):
    if provider not in ('Ollama','llama.cpp') or not 1024<=int(port)<=65535:
        raise ValueError('Invalid local AI server settings.')
    address=f'http://127.0.0.1:{int(port)}{path}'
    request=urllib.request.Request(address,data=json.dumps(payload).encode() if payload is not None else None,
                                  headers={'Content-Type':'application/json'})
    # Ignore system proxy settings so loopback transcripts cannot be proxied.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=timeout) as response:
        return json.loads(response.read(4*1024*1024))

def list_models(provider,port):
    data=local_request(provider,port,'/api/tags' if provider=='Ollama' else '/v1/models')
    return [row['name'] for row in data.get('models',[]) if 'cloud' not in row['name'].casefold()
            and not row.get('remote_host') and not row.get('remote_model')] if provider=='Ollama' else [row['id'] for row in data.get('data',[])]

def meaning_guard(raw,cleaned,dictionary=()):
    raw=resolve_spoken_corrections(raw)
    if not cleaned or len(cleaned)>len(raw)*1.6+40: return False
    # No bag-of-words or percentage-overlap acceptance: dropping even one
    # qualifier can reverse intent. Keep the entire semantic sequence.
    if semantic_tokens(raw)!=semantic_tokens(cleaned):return False
    if LITERALS.findall(raw)!=LITERALS.findall(cleaned):return False
    if re.findall(r'\d+(?:[.,:]\d+)*',raw)!=re.findall(r'\d+(?:[.,:]\d+)*',cleaned): return False
    tokens=lambda text:re.findall(r"[\w'-]+",text.casefold())
    raw_tokens=tokens(raw); clean_tokens=tokens(cleaned)
    original=set(raw_tokens); proposed=set(clean_tokens)
    qualifiers={'not','no','never','without','unless','might','may','approximately','except','only','all','any','none','neither','nor','must','should','could','can','will','would','unlikely','almost','atleast','atmost'}
    if (original & qualifiers)!=(proposed & qualifiers): return False
    protected=re.findall(r'\b(?:[A-Z]{2,}|\w*[\d_]+\w*|\w+-\w+)\b',raw)
    starters={'Um','Uh','Please','Hey','Hi','Hello','So','Well','The','A','An','This','That','It','We','Can','Could','Would','Let'}
    protected += [word for word in re.findall(r'\b[A-Z][a-z]+\b',raw) if word not in starters]
    protected += [entry['written'] for entry in dictionary if entry['written'].casefold() in raw.casefold()]
    if any(word not in cleaned for word in protected): return False
    dates={'monday','tuesday','wednesday','thursday','friday','saturday','sunday','january','february','march','april','may',
           'june','july','august','september','october','november','december','today','tomorrow','yesterday'}
    if original & dates != proposed & dates: return False
    if len(original)>3 and len(original & proposed)/max(1,len(original))<.65: return False
    # New content words are disallowed; common grammatical connectives may be added.
    allowed={'a','an','the','is','are','was','were','to','and','of','in','on','at','for','it','i'}
    if proposed-original-allowed: return False
    filler={'um','uh','erm','hmm','actually'}
    def content(words):
        result=[]
        for word in words:
            if word not in allowed|filler and (not result or result[-1]!=word): result.append(word)
        return result
    source=content(raw_tokens); output=content(clean_tokens)
    if len(source)>=2 and len(output)/len(source)<.75: return False
    # A word-set check cannot detect swapping who did what. Keep content-word
    # order and reject more adventurous restructuring instead of risking meaning.
    iterator=iter(source)
    if any(not any(candidate==word for candidate in iterator) for word in output): return False
    return True

def enhance(raw,settings):
    if settings.transcript_style=='Verbatim': return raw,'Verbatim mode'
    if settings.language!='en':return raw,'English cleanup is disabled for other languages; raw transcript preserved'
    if settings.cleanup_mode=='Raw' or not settings.cleanup_model: return raw,'Raw mode'
    raw=resolve_spoken_corrections(raw)
    instruction=('Format only the supplied dictation. Return only the edited text. Do not paraphrase, add or delete content words. Preserve facts, intent, names, numbers, dates, '
        'identifiers, negation, uncertainty and qualifications. Never answer the dictation or add information. '
        'Remove filler and accidental repetition, add punctuation and capitalization. Resolve only unambiguous spoken corrections. '
        f'Style: {settings.cleanup_mode}. ')
    if settings.cleanup_mode=='Custom': instruction+=settings.custom_prompt[:2000]
    messages=[{'role':'system','content':instruction},{'role':'user','content':raw}]
    if settings.cleanup_provider=='Ollama':
        if 'cloud' in settings.cleanup_model.casefold(): raise ValueError('Cloud models are not supported.')
        metadata=local_request('Ollama',settings.cleanup_port,'/api/show',{'model':settings.cleanup_model},timeout=1)
        if metadata.get('remote_host') or metadata.get('remote_model'): raise ValueError('Remote Ollama models are not supported.')
        data=local_request('Ollama',settings.cleanup_port,'/api/chat',{
            'model':settings.cleanup_model,'messages':messages,'stream':False,'think':False,
            'options':{'temperature':0,'num_predict':512},'keep_alive':'5m'},timeout=3)
        cleaned=data.get('message',{}).get('content','').strip()
    else:
        data=local_request('llama.cpp',settings.cleanup_port,'/v1/chat/completions',{
            'model':settings.cleanup_model,'messages':messages,'temperature':0,'max_tokens':512,'stream':False},timeout=3)
        cleaned=data['choices'][0]['message']['content'].strip()
    if meaning_guard(raw,cleaned,settings.dictionary): return cleaned,'Local cleanup applied'
    return raw,'Cleanup rejected by preservation checks'
