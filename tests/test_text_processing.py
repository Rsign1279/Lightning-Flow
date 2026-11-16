"""User-visible audit regressions, including meaning-changing edits."""
import threading
import time
from dataclasses import replace
import numpy as np
import pytest
from lightningflow.text_processing import resolve_spoken_corrections,boundary_spacing
from lightningflow.desktop.cleanup import meaning_guard
from lightningflow.desktop.personalization import prepare_transcript
from lightningflow.desktop.state import Settings,Preferences
from lightningflow.audio import PreviewBuffer,Segmenter,BLOCK,RATE
from lightningflow.win32 import EditText,spaced_insertion


@pytest.mark.parametrize('raw,edited',[
    ('Please approve only the draft for Friday.','Please approve the draft for Friday.'),
    ('There is no refund available for this purchase.','There is a refund available for this purchase.'),
    ('We are unlikely to deliver on Friday.','We are to deliver on Friday.'),
    ('We can send all copies to John.','We can send copies to John.'),
    ('We can send some copies to John.','We can send all copies to John.'),
    ('I paid more than 5 dollars.','I paid 5 dollars.'),
    ('Please send from John to Mary.','Please send to John from Mary.'),
    ('The limit is < 5 percent.','The limit is > 5 percent.'),
    ('No, no, send the report.','No, send the report.'),
    ('Use version 1.2.','Use version 12.'),
    ('Keep `no only` exactly.','Keep `only` exactly.'),
])
def test_no_semantic_word_can_disappear_or_change_role(raw,edited):
    assert not meaning_guard(raw,edited)


@pytest.mark.parametrize('raw,written',[
    ("Let's meet tomorrow, actually Friday at 3.","Let's meet Friday at 3."),
    ('Meet on Friday, no, Saturday.','Meet on Saturday.'),
    ('Use port 8000, no, 8080.','Use port 8080.'),
    ('Meet at 2 actually 3.','Meet at 3.'),
    ('Meet at three, actually four.','Meet at four.'),
    ('Meet next Monday, make that Friday.','Meet Friday.'),
    ('Set it to 20 percent, actually 30 percent.','Set it to 30 percent.'),
    ('Meet tomorrow actually no Friday at three.','Meet Friday at three.'),
])
def test_explicit_same_type_corrections(raw,written):
    assert resolve_spoken_corrections(raw)==written
    assert meaning_guard(raw,written)
    assert prepare_transcript(raw,Settings())==written
    assert prepare_transcript(raw,Settings(transcript_style='Verbatim'))==raw


@pytest.mark.parametrize('raw',[
    'I actually enjoyed Friday.',
    'There is no refund for Friday.',
    'Not Friday, actually Saturday.',
    'No Friday, actually Saturday.',
    'Meet Friday, actually I cannot go.',
    'Use 5, actually I need five different sensors.',
    'Keep "tomorrow, actually Friday" literal.',
    'Use `8000, no, 8080` as an example.',
    "He said 'tomorrow, actually Friday'.",
    'Meet Friday, no later than Saturday.',
    'Finish tomorrow, actually Friday is a holiday.',
    'Meet the day before tomorrow, actually Friday.',
])
def test_ambiguous_negated_or_literal_corrections_stay(raw):
    assert resolve_spoken_corrections(raw)==raw


def test_multiword_personal_names_only_resolve_when_both_are_known():
    raw='Send to Alex Smith, no, Jamie Jones.'
    assert resolve_spoken_corrections(raw)==raw
    assert resolve_spoken_corrections(raw,['Alex Smith','Jamie Jones'])=='Send to Jamie Jones.'
    assert resolve_spoken_corrections(raw,['Alex Smith'])==raw


@pytest.mark.parametrize('prefix,suffix,text,expected',[
    ('First sentence.','','Second sentence.',' Second sentence.'),
    ('hello','','world',' world'),('hello ','','world','world'),
    ('hello','',' world',' world'),('hello','world','middle','middle'),
    ('','there','Hello','Hello '),('',' there','Hello','Hello'),
    ('😀','','Hello','Hello'),('你好','','世界','世界'),
    ('https://example.','','com','com'),('version 1.','','2','2'),
    ('object.','','method','method'),
    ('call(','','argument','argument'),('Hi!','','Again',' Again'),
])
def test_prose_boundary_spacing_and_literals(prefix,suffix,text,expected):
    assert boundary_spacing(prefix,suffix,text)==expected


def test_native_spacing_uses_utf16_not_python_character_offsets():
    state=EditText('😀 Hello.',9,9)
    assert spaced_insertion(state,'Again')==' Again'


def test_multilingual_models_are_explicit_and_do_not_apply_english_filler_rules():
    settings=Settings(model='base',language='de').validate()
    assert prepare_transcript('Wir treffen uns um drei.',settings)=='Wir treffen uns um drei.'
    with pytest.raises(ValueError,match='multilingual'):Settings(model='base.en',language='de').validate()
    assert Settings(model='base',language='auto').validate()


def test_preview_arrives_before_final_without_changing_authoritative_audio():
    preview=PreviewBuffer();segment=Segmenter();first=None;frames=[]
    for n in range(400):
        frame=np.full(BLOCK,.1,dtype=np.float32);frames.append(frame)
        sample=preview.feed(frame)
        if sample is not None:
            first=first or (n+1)*BLOCK/RATE
            assert len(sample)<=4*RATE
        chunk=segment.feed(frame)
        if n<399:assert chunk is None
    assert first==pytest.approx(.8)
    assert np.array_equal(chunk.audio,np.concatenate(frames))
    assert preview.samples<=4*RATE


def test_silent_preview_is_suppressed_and_reset_removes_old_audio():
    preview=PreviewBuffer()
    for _ in range(200):assert preview.feed(np.zeros(BLOCK,dtype=np.float32)) is None
    preview.reset()
    assert not preview.frames and not preview.voiced


def test_background_ai_never_delays_or_revises_inserted_text(tmp_path,monkeypatch):
    from lightningflow.desktop import worker
    from lightningflow.desktop.worker import build_backend
    release=threading.Event();done=threading.Event();sent=[]
    def delayed(raw,settings):
        release.wait(2);done.set();return 'Original dictation.','Local cleanup applied'
    monkeypatch.setattr('lightningflow.desktop.cleanup.enhance',delayed)
    monkeypatch.setattr(worker,'send',lambda kind,**data:sent.append((kind,data)))
    path=tmp_path/'settings.json'
    Preferences(path).save(Settings(cleanup_mode='Smart cleanup',cleanup_model='local-test'))
    backend=build_backend(path,tmp_path/'models')
    session=backend.new_session(None);session.text='original dictation';backend.active=session
    start=time.perf_counter();backend.schedule_delivery(session)
    assert time.perf_counter()-start<.1
    assert backend.pending[0] is session and backend.cleanup_pending is None
    assert not release.is_set()
    session.result_emitted=True;session.delivered=True
    release.set();assert done.wait(1)
    deadline=time.perf_counter()+1
    while not any(kind=='suggestion' for kind,_ in sent) and time.perf_counter()<deadline:
        backend.on_tick();time.sleep(.002)
    assert any(kind=='suggestion' for kind,_ in sent)
    assert session.text=='original dictation' and session.delivered
