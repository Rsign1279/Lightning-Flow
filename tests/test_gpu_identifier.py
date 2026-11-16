import pytest
from lightningflow.desktop.personalization import correct_vocabulary


@pytest.fixture
def profile():
    return {'vocabulary':['RTX 5070','RTX 5090','RTX 4090'],
            'canonical':[],'rules':[],'corrections':[]}


@pytest.mark.parametrize('raw,wanted',[
    ('The RTX 5000 and 70 runs CUDA.','The RTX 5070 runs CUDA.'),
    ('My RTX 5000 and 90 has 32 GB.','My RTX 5090 has 32 GB.'),
    ('The RTX 4000 and 90 is available.','The RTX 4090 is available.'),
    ('Use the rtx 5000 and 70 GPU.','Use the RTX 5070 GPU.'),
    ('The RTX 5000 and 70 runs at 87.2%, not 90.96%.','The RTX 5070 runs at 87.2%, not 90.96%.'),
    ('The RTX 5070 runs CUDA.','The RTX 5070 runs CUDA.'),
    ('The RTX 500070 runs CUDA.','The RTX 5070 runs CUDA.'),
    ('The RTX500070 runs CUDA.','The RTX 5070 runs CUDA.'),
    ('The RTX 500090 has 32 GB.','The RTX 5090 has 32 GB.'),
    ('Use RTX5070.','Use RTX 5070.'),
    ('Use RTX5070.cfg.','Use RTX5070.cfg.'),
    ('The literal RTX5070 is a string.','The literal RTX5070 is a string.'),
    ('The literal RTX 500070 runs CUDA.','The literal RTX 500070 runs CUDA.'),
    ('The serial RTX 500070 runs CUDA.','The serial RTX 500070 runs CUDA.'),
    ('The number 500070 runs through this formula.','The number 500070 runs through this formula.'),
    ('The RTX 500070 and RTX 5090 are separate.','The RTX 500070 and RTX 5090 are separate.'),
    ('The RTX 500080 runs CUDA.','The RTX 500080 runs CUDA.'),
    ('The RTX 5090 runs CUDA.','The RTX 5090 runs CUDA.'),
    ('RTX 5000 and 70 are different cards.','RTX 5000 and 70 are different cards.'),
    ('The RTX 5000 and RTX 70 run CUDA.','The RTX 5000 and RTX 70 run CUDA.'),
    ('The RTX 5000 and 70 cards run CUDA.','The RTX 5000 and 70 cards run CUDA.'),
    ('The RTX 5000 and 70 GPUs are separate.','The RTX 5000 and 70 GPUs are separate.'),
    ('The RTX 5000 and 70 graphics cards are separate.','The RTX 5000 and 70 graphics cards are separate.'),
    ('RTX 5000 and 70.','RTX 5000 and 70.'),
    ('RTX 5000 and 70.5 runs CUDA.','RTX 5000 and 70.5 runs CUDA.'),
    ('RTX 5000 and 70-2 runs CUDA.','RTX 5000 and 70-2 runs CUDA.'),
    ('RTX 5000 and 70, runs CUDA.','RTX 5000 and 70, runs CUDA.'),
    ('5000 and 70 runs CUDA.','5000 and 70 runs CUDA.'),
    ('The RTX 5000 and 80 runs CUDA.','The RTX 5000 and 80 runs CUDA.'),
    ('The RTX 5000 and 700 runs CUDA.','The RTX 5000 and 700 runs CUDA.'),
    ('Use `RTX 5000 and 70 runs CUDA`.','Use `RTX 5000 and 70 runs CUDA`.'),
    ('```RTX 5000 and 70 runs CUDA```','```RTX 5000 and 70 runs CUDA```'),
    ('my_RTX 5000 and 70 runs CUDA.','my_RTX 5000 and 70 runs CUDA.'),
    ('The string "RTX 5000 and 70 runs CUDA" is literal.','The string "RTX 5000 and 70 runs CUDA" is literal.'),
    ("print('RTX 5000 and 70 runs CUDA')","print('RTX 5000 and 70 runs CUDA')"),
])
def test_known_GPU_identifier_rendering_is_contextual(profile,raw,wanted):
    assert correct_vocabulary(raw,profile)==wanted


def test_no_profile_has_no_identifier_repair():
    raw='The RTX 5000 and 70 runs CUDA.'
    assert correct_vocabulary(raw,{})==raw


def test_no_known_model_has_no_identifier_repair(profile):
    profile['vocabulary']=['RTX 5090']
    raw='The RTX 5000 and 70 runs CUDA.'
    assert correct_vocabulary(raw,profile)==raw


@pytest.mark.parametrize('style,enabled,wanted',[
    ('Verbatim',True,'Um, the RTX 5070 runs CUDA.'),
    ('Clean',True,'The RTX 5070 runs CUDA.'),
    ('Verbatim',False,'Um, the RTX 500070 runs CUDA.'),
])
def test_identifier_respects_transcript_style_and_profile_switch(profile,style,enabled,wanted):
    from lightningflow.desktop.state import Settings
    from lightningflow.desktop.personalization import prepare_transcript
    settings=Settings(voice_profile=profile,personalization_enabled=enabled,transcript_style=style)
    assert prepare_transcript('Um, the RTX 500070 runs CUDA.',settings)==wanted
