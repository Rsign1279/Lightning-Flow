"""Bounded, deterministic dictation edits. No model, network or user state."""
import re

# Quoted material and code are literal. Apostrophes inside words are not quotes.
LITERALS = re.compile(r'(```[\s\S]*?```|`[^`\n]*`|"[^"\n]*"|“[^”\n]*”|(?<!\w)\x27[^\x27\n]+\x27(?!\w))')
DAY = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|today|tomorrow|yesterday|tonight)'
TEMPORAL = rf'(?:(?:next|this|last)\s+)?{DAY}'
NUMBER_WORD = r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)'
NUMBER = rf'(?:\d+(?:[.,]\d+)*(?::\d{{2}})?|{NUMBER_WORD}(?:[- ]{NUMBER_WORD}){{0,5}})(?:\s?(?:a\.?m\.?|p\.?m\.?|percent|%))?'
MARKER = re.compile(r'\s*,?\s*\b(?:actually\s*,?\s*(?:no\s*,?\s*)?|no\s*,\s*|make that\s+|I mean\s*,?\s*)',re.I)
NEGATED = re.compile(r"\b(?:not|no|never|without|except|unless|neither|nor|only)\s*$",re.I)


def _correct_clause(text,terms=()):
    # A correction must replace a bounded value with another value of the same
    # type. Never discard an arbitrary preceding clause or guess what 'that' is.
    for _ in range(8):
        changed = False
        for marker in MARKER.finditer(text):
            left,right = text[:marker.start()],text[marker.end():]
            patterns=[TEMPORAL,NUMBER]
            if terms:patterns.append('(?:'+'|'.join(re.escape(term) for term in terms)+')')
            for value in patterns:
                before=re.search(rf'(?<![\w-])({value})$',left,re.I)
                after=re.match(rf'({value})(?![\w-])',right,re.I)
                if not before or not after:continue
                if NEGATED.search(left[:before.start()]):continue
                if re.search(r'\b(?:before|after|until|between|more than|less than|at least|at most)\s*$',left[:before.start()],re.I):continue
                if re.match(r'\s+(?:is|are|was|were|has|have|had|does|did|will|might|cannot|can|seems|means)\b',right[after.end():],re.I):continue
                # A comma followed by a new clause is not a value replacement.
                # A trailing unit belongs to the replacement and stays verbatim.
                text=left[:before.start()]+after.group(1)+right[after.end():]
                changed=True
                break
            if changed:break
        if not changed:break
    return text


def resolve_spoken_corrections(text,terms=()):
    """Resolve explicit date/time/number corrections; preserve ambiguous speech."""
    terms=sorted({term for term in terms if isinstance(term,str) and 0<len(term)<=120},key=len,reverse=True)[:500]
    parts=LITERALS.split(text)
    for index in range(0,len(parts),2):
        parts[index]=_correct_clause(parts[index],terms)
    return ''.join(parts)


def semantic_tokens(text):
    """Keep every meaningful word, operator and contraction in order.

    Only hesitation sounds and a small set of adjacent function-word stutters
    can disappear. In particular 'no', 'only', prepositions, modal verbs and
    all quantifiers remain part of the sequence, including their multiplicity.
    """
    text=text.replace('’',"'").casefold()
    contractions={"can't":"can not","cannot":"can not","won't":"will not",
                  "isn't":"is not","aren't":"are not","wasn't":"was not",
                  "weren't":"were not","don't":"do not","doesn't":"does not",
                  "didn't":"did not","shouldn't":"should not","wouldn't":"would not",
                  "couldn't":"could not","mustn't":"must not"}
    for original,expanded in contractions.items():
        text=re.sub(r'(?<!\w)'+re.escape(original)+r'(?!\w)',expanded,text)
    words=re.findall(r"[\w]+(?:['-][\w]+)*|[<>≤≥≠=+±%/\\@]",text)
    result=[]
    stutters={'the','a','an','to','of','in','on','at','for','is','are','was','were'}
    for word in words:
        if word in {'um','uh','erm','hmm'}:continue
        if result and word==result[-1] and word in stutters:continue
        result.append(word)
    return result


def boundary_spacing(prefix,suffix,text):
    """Add separators to prose at a collapsed caret without changing words.

    Preserve explicit whitespace, code/path/URL continuations, decimal points,
    CJK and mid-word insertions. Only the inserted payload gains whitespace.
    """
    if not text:return text
    def cjk(c):return '\u2e80'<=c<='\u9fff' or '\uac00'<=c<='\ud7af' or '\uf900'<=c<='\ufaff'
    def word(c):return c.isalnum() or c=='_'
    if prefix and suffix and word(prefix[-1]) and word(suffix[0]):return text
    last=prefix.rsplit(None,1)[-1] if prefix and not prefix[-1].isspace() else ''
    technical=bool(re.search(r'://|[@/\\]|[_=]|\w\.[\w.]+$',last))
    technical|=bool(last.endswith('.') and last[:-1].isidentifier() and text[0].islower())
    decimal=bool(re.search(r'\d\.$',prefix) and text[0].isdigit())
    if (prefix and not prefix[-1].isspace() and not text[0].isspace()
            and word(text[0]) and (word(prefix[-1]) or prefix[-1] in '.!?;:)]}”"')
            and not cjk(prefix[-1]) and not cjk(text[0]) and not technical and not decimal):
        text=' '+text
    if (suffix and not suffix[0].isspace() and not text[-1].isspace()
            and word(suffix[0]) and (word(text[-1]) or text[-1] in '.!?;:)]}”"')
            and not cjk(suffix[0]) and not cjk(text[-1]) and not technical):
        text+=' '
    return text
