"""Local vocabulary data, bounded ASR hints and conservative text transforms.

Imported prose is never an instruction/prompt. Biography and metric context
are deliberately excluded. No fuzzy substitutions or acoustic training.
"""
from copy import deepcopy
import json
from pathlib import Path
import re

MAX_BYTES = 256 * 1024
AMBIGUOUS = {'PATHOS','EverGreen','AIM','IGNITE','LOSO','LASSO','R','BHS','UI','UX','AIF','PEY','BCS','BBA'}
RULES = {
    'PATHOS': (('pathos','pay those','pesos'),
        (('wearable','stress','eda','ppg','wesad','we sad','way sad'),('model','project','sensor','sensors','company'))),
    'EverGreen': (('ever green','evergreen'), (('recycling','recycle'),('system','sorting','kiosk','project'))),
    'WESAD': (('way sad','we sad','wes ad','wesad'),
        (('dataset','validation','evaluation'),('stress','wearable','loso','low so','loss oh','pathos'))),
    'LASSO': (('lasso','last so'), (('regression','feature selection','regularization'),)),
    'LOSO': (('low so','loss oh','loso'), (('validation','evaluation','leave-one-subject-out'),)),
    'I2C': (('i squared c','eye two see','i2c'), (('bus','electronics','sensor','sensors','gpio','esp32','microcontroller'),)),
    'OUAC': (('oh you ack','ouac'), (('ontario','university','admissions','application','applications'),)),
    'AIF': (('a i f','aif'), (('waterloo','admissions','application','applications'),)),
}


def phrase_pattern(phrases):
    return re.compile(r'(?<![\w-])(?:'+'|'.join(re.escape(x) for x in sorted(phrases,key=len,reverse=True))+r')(?![\w-])',re.I)


def contains(text,phrase):
    return bool(phrase_pattern([phrase]).search(text))


def nearby_clause(text,start,end):
    before=re.split(r'[.!?;\n]',text[:start])[-1][-128:]
    after=re.split(r'[.!?;\n]',text[end:])[0][:128]
    return before+text[start:end]+after


def import_bank(path, prompt_path=None):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES: raise ValueError('Knowledge bank must be smaller than 256 KiB.')
    bank=json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(bank,dict) and bank.get('version')==1:
        return validate_profile({k:bank[k] for k in ('version','title','vocabulary','priority','canonical','rules','corrections') if k in bank})
    if not isinstance(bank,dict) or bank.get('schema_version')!='1.0': raise ValueError('Choose a version 1.0 JSON knowledge bank.')
    groups=bank.get('priority_vocabulary')
    if not isinstance(groups,dict): raise ValueError('Knowledge bank needs priority_vocabulary groups.')
    words=[];canonical=[]
    for category,terms in groups.items():
        if not isinstance(terms,list): raise ValueError('Vocabulary groups must contain lists of terms.')
        for term in terms:
            if not isinstance(term,str) or not 1<=len(term.strip())<=120 or any(ord(c)<32 for c in term) or '<|' in term or '|>' in term:
                raise ValueError('Vocabulary terms must be short, single-line text.')
            term=term.strip()
            if term not in words: words.append(term)
            # Exact spelling/case only. Common short words and ambiguous project
            # names need contextual rules instead of unconditional capitalization.
            if (term not in AMBIGUOUS and (category in ('identity','people_from_prior_discussions')
                    or (len(term)>3 and (term.isupper() or any(c.isdigit() for c in term)))
                    or term in ('University of Waterloo','University of Toronto','Ollama','Codex','Obsidian','GitHub','Whisper'))):
                canonical.append(term)
    # Use the supplied compact list only to rank known vocabulary, never as an
    # executable instruction. Unknown words/prose are not sent to Whisper.
    priority=[]
    if prompt_path:
        prompt_path=Path(prompt_path)
        if prompt_path.stat().st_size>16384: raise ValueError('Compact vocabulary prompt must be smaller than 16 KiB.')
        prompt=prompt_path.read_text(encoding='utf-8-sig')
        priority=sorted((w for w in words if contains(prompt,w)),key=lambda w:(prompt.casefold().find(w.casefold()),-len(w)))
    rules=[]
    for rule in bank.get('disambiguation',[]):
        if isinstance(rule,dict) and rule.get('prefer') in RULES and rule['prefer'] in words and rule['prefer'] not in rules:
            rules.append(rule['prefer'])
    profile={'version':1,'title':str(bank.get('title','Personal vocabulary'))[:128],
             'vocabulary':words,'priority':priority,'canonical':list(dict.fromkeys(canonical)),
             'rules':rules,'corrections':[]}
    return validate_profile(profile)


def validate_profile(profile):
    if not isinstance(profile,dict): raise ValueError('Invalid personal vocabulary.')
    if not profile:return {}
    if profile.get('version')!=1: raise ValueError('Unsupported personal vocabulary version.')
    if len(json.dumps(profile,ensure_ascii=False).encode())>MAX_BYTES: raise ValueError('Personal vocabulary is too large.')
    if not isinstance(profile.get('title'),str) or len(profile['title'])>128: raise ValueError('Invalid vocabulary title.')
    for name in ('vocabulary','priority','canonical'):
        items=profile.get(name)
        if not isinstance(items,list) or len(items)>500 or any(not isinstance(v,str) or not 1<=len(v)<=120 or any(ord(c)<32 for c in v) or '<|' in v or '|>' in v for v in items):
            raise ValueError('Vocabulary supports up to 500 short terms.')
    if not set(profile['priority']+profile['canonical'])<=set(profile['vocabulary']): raise ValueError('Unknown preferred term.')
    if not isinstance(profile.get('rules'),list) or any(r not in RULES or r not in profile['vocabulary'] for r in profile['rules']): raise ValueError('Invalid contextual rule.')
    corrections=profile.get('corrections')
    if not isinstance(corrections,list) or len(corrections)>200: raise ValueError('At most 200 explicit corrections are supported.')
    for rule in corrections:
        if not isinstance(rule,dict) or set(rule)!={'spoken','written','context'}: raise ValueError('Invalid saved correction.')
        if any(not isinstance(rule[n],str) or not 1<=len(rule[n].strip())<=120 or any(ord(c)<32 for c in rule[n]) for n in rule): raise ValueError('Corrections need a phrase, spelling and context (1–120 characters each).')
        if numeric_tokens(rule['spoken'])!=numeric_tokens(rule['written']): raise ValueError('Learned corrections cannot change numeric values.')
    return profile


def numeric_tokens(text):return re.findall(r'\d+(?:[.,:]\d+)*',text)


def hint_text(profile,dictionary=()):
    if not profile and not dictionary:return ''
    terms=[e['written'] for e in dictionary]
    terms+=profile.get('priority',[])+profile.get('vocabulary',[])
    terms=list(dict.fromkeys(terms))
    # Actual tokenizer cap is applied by CudaASR once per distinct hint string.
    result=[];size=0
    for term in terms:
        if '<|' in term or '|>' in term:continue
        if size+len(term)+2>1800:break
        result.append(term);size+=len(term)+2
    return ', '.join(result)


def format_gpu_identifier(text,profile):
    """Normalize known RTX identifier spellings in singular hardware context.

    Handles additive words and the observed concatenated ASR form (500070).
    Both resolve only to a model already in the enabled vocabulary. This is
    identifier correction, not a general numeric-value rewrite. Lists, quoted
    literals, bare numbers, decimals and plural constructions are preserved.
    """
    models={int(m.group(1)) for term in profile.get('vocabulary',[]) if (m:=re.fullmatch(r'RTX\s+(\d{4})',term,re.I))}
    if not models:return text
    pattern=re.compile(r'(?<![\w-])RTX[ \t]*([1-9]000)(?:[ \t]+and[ \t]+|(?=\d))(\d{1,3})(?![\w.-])'
                       r'(?=[ \t]+(?:runs|uses|is|has|supports|GPU|graphics card|card)\b)',re.I)
    parts=re.split(r'("[^"\n]*"|“[^”\n]*”|(?<!\w)\x27[^\x27\n]*\x27(?!\w))',text)
    exact=re.compile(r'(?<![\w-])RTX[ \t]*(\d{4})(?![\w-]|\.\w)',re.I)
    for i in range(0,len(parts),2):
        # Keep offsets relative to this unquoted part for literal-context checks.
        part=parts[i]
        def replace_part(match):
            context=nearby_clause(part,match.start(),match.end())
            if re.search(r'\b(?:literal|serial|string|verbatim)\b|exact digits',context,re.I):return match[0]
            value=int(match[1])+int(match[2])
            return f'RTX {value}' if value in models else match[0]
        part=pattern.sub(replace_part,part)
        def replace_exact(match):
            context=nearby_clause(part,match.start(),match.end())
            if re.search(r'\b(?:literal|serial|string|verbatim)\b|exact digits',context,re.I):return match[0]
            return f'RTX {int(match[1])}' if int(match[1]) in models else match[0]
        parts[i]=exact.sub(replace_exact,part)
    return ''.join(parts)


def correct_vocabulary(text,profile):
    if not profile:return text
    # Never change fenced code or inline identifiers. Whole-word boundaries
    # also exclude underscored/hyphenated identifiers from partial matches.
    parts=re.split(r'(```[\s\S]*?```|`[^`\n]*`)',text)
    for index in range(0,len(parts),2):
        original=format_gpu_identifier(parts[index],profile);updates=[]
        for term in profile['canonical']:
            for match in phrase_pattern([term]).finditer(original): updates.append((match.start(),match.end(),term))
        for name in profile['rules']:
            aliases,groups=RULES[name]
            for match in phrase_pattern(aliases).finditer(original):
                context=nearby_clause(original,match.start(),match.end())
                if all(any(contains(context,anchor) for anchor in group) for group in groups):
                    updates.append((match.start(),match.end(),name))
        for rule in profile['corrections']:
            for match in phrase_pattern([rule['spoken']]).finditer(original):
                if contains(nearby_clause(original,match.start(),match.end()),rule['context']):
                    updates.append((match.start(),match.end(),rule['written']))
        # One pass, longest span wins; explicit correction wins equal spans.
        by_start={}
        for a,b,value in updates:
            if a not in by_start or b>=by_start[a][0]:by_start[a]=(b,value)
        cursor=0;out=[]
        for a,(b,value) in sorted(by_start.items()):
            if a<cursor:continue
            out.extend((original[cursor:a],value));cursor=b
        out.append(original[cursor:]);parts[index]=''.join(out)
    return ''.join(parts)


def clean_hesitations(text):
    # "Like", "right", "actually", intensifiers and restarts may carry real
    # meaning. Only standalone hesitation sounds are removed offline.
    parts=re.split(r'(```[\s\S]*?```|`[^`\n]*`)',text)
    for i in range(0,len(parts),2):
        value=parts[i]
        # Quoted speech is literal too; preserve it rather than editing a quote.
        if re.search(r'["“”]|(?<!\w)\x27[^\x27\n]*\x27(?!\w)|\b\w+\s*=|[{}]',value):continue
        fillers=r'(?:[Uu]m|[Uu]h|[Ee]rm|[Hh]mm)'
        leading=bool(re.match(r'^'+fillers+r'(?![\w-])',value))
        value=re.sub(r'(?<![\w.\x27-])'+fillers+r'(?![\w-]|[ \t]*[=(])[,;:]?[ \t]*','',value)
        if leading and value and value[0].islower():value=value[0].upper()+value[1:]
        parts[i]=value
    return ''.join(parts).strip()


def add_correction(profile,spoken,written,context):
    if not profile:raise ValueError('Import a knowledge bank before saving a contextual correction.')
    result=deepcopy(profile)
    rule={'spoken':spoken.strip(),'written':written.strip(),'context':context.strip()}
    result['corrections']=[r for r in result['corrections'] if (r['spoken'].casefold(),r['context'].casefold())!=(rule['spoken'].casefold(),rule['context'].casefold())]+[rule]
    return validate_profile(result)


def prepare_transcript(raw,settings):
    from .state import apply_dictionary
    text=correct_vocabulary(raw,settings.voice_profile) if settings.personalization_enabled else raw
    text=apply_dictionary(text,settings.dictionary)
    if settings.transcript_style=='Clean' and settings.language=='en':
        from ..text_processing import resolve_spoken_corrections
        terms=settings.voice_profile.get('vocabulary',[]) if settings.personalization_enabled else []
        terms=list(terms)+[entry['written'] for entry in settings.dictionary]
        return resolve_spoken_corrections(clean_hesitations(text),terms)
    return text
