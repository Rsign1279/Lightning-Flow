from types import SimpleNamespace as Obj
import pytest
from lightningflow.accessibility import _read


def fixture(document_text,value,prefix,readonly=False,framework=''):
    selected=Obj(GetText=lambda _:'')
    document=Obj(GetText=lambda _:document_text,GetAttributeValue=lambda _:False,
        Clone=lambda:Obj(MoveEndpointByRange=lambda *_:None,GetText=lambda _:prefix))
    text=Obj(DocumentRange=document,GetSelection=lambda:Obj(Length=1,GetElement=lambda _:selected))
    val=Obj(CurrentValue=value,CurrentIsReadOnly=readonly)
    def get(kind):
        if kind==10002 and value is None:raise RuntimeError('No ValuePattern')
        return Obj(QueryInterface=lambda _:text if kind==10014 else val)
    element=Obj(CurrentHasKeyboardFocus=True,CurrentIsPassword=False,CurrentIsEnabled=True,CurrentFrameworkId=framework,
        GetCurrentPattern=get,GetRuntimeId=lambda:(1,2),CurrentProcessId=3)
    return Obj(GetFocusedElement=lambda:element),Obj(IUIAutomationTextPattern=object(),IUIAutomationValuePattern=object())


def test_actual_editor_value_excludes_phantom_final_paragraph():
    automation,module=fixture('marker\n\n','marker\r\n','marker\n')
    state=_read(automation,module)
    assert state.text=='marker\n' and state.start==state.end==7


def test_value_pattern_cannot_override_inconsistent_selection():
    automation,module=fixture('marker\n\n','different','marker\n')
    with pytest.raises(RuntimeError,match='inconsistent'):_read(automation,module)


def test_text_only_provider_remains_supported():
    automation,module=fixture('marker',None,'marker')
    assert _read(automation,module).text=='marker'


def test_value_readonly_target_is_refused():
    automation,module=fixture('marker','marker','marker',readonly=True)
    with pytest.raises(RuntimeError,match='Read-only'):_read(automation,module)


def test_chromium_empty_final_line_sentinel_is_not_document_content():
    automation,module=fixture('marker\n\n','marker\n\n','marker\n',framework='Chrome')
    assert _read(automation,module).text=='marker\n'


def test_chromium_real_blank_paragraphs_are_preserved():
    automation,module=fixture('marker\n\n\n','marker\n\n\n','marker\n',framework='Chrome')
    assert _read(automation,module).text=='marker\n\n\n'
    automation,module=fixture('marker\n\n\n','marker\n\n\n','marker\n\n',framework='Chrome')
    assert _read(automation,module).text=='marker\n\n'


def test_other_framework_does_not_trim_a_trailing_paragraph():
    automation,module=fixture('marker\n\n','marker\n\n','marker\n',framework='WPF')
    assert _read(automation,module).text=='marker\n\n'


def test_legacy_value_truncation_keeps_full_verified_text_pattern():
    complete='a'*4096+' rest of the document'
    automation,module=fixture(complete,complete[:4096],complete,framework='Win32')
    state=_read(automation,module)
    assert state.text==complete and state.start==len(complete)


def test_legacy_truncation_counts_utf16_and_cannot_hide_disagreement():
    complete='😀'*2048+' remaining text'
    automation,module=fixture(complete,complete[:2048],complete,framework='Win32')
    assert _read(automation,module).text==complete
    automation,module=fixture(complete,'a'*4096,complete,framework='Win32')
    with pytest.raises(RuntimeError,match='inconsistent'):_read(automation,module)
