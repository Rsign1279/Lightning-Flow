# Models and evidence

Implemented runtime: faster-whisper/CTranslate2 CUDA, resident in one inference worker. English choices: tiny.en, base.en, small.en. Multilingual choices: tiny, base, small; select a supported Whisper language code or auto. English-only models reject other language choices. Downloads are explicit and need no account. English-specific deterministic/AI cleanup is disabled for other recognition languages.

English tiny.en and base.en FP16 and small.en/int8_float16 have executed on the development RTX 5070. Multilingual selections have settings/decoder contract coverage but have not been downloaded or quality-benchmarked for this release. Fast/Balanced/Accurate are labels, not a universal ranking. Quantization is optional and is not assumed faster or more accurate.

The 0.5.0 gesture run used one small.en/int8_float16 model over 200 synthetic sessions. A separate two-session real-time replay compared previews on/off with identical final text. See FIXES_0.5.0.md. Historical base.en/tiny.en results remain in PERFORMANCE.md and DECODER_FIX.md; they do not establish human accuracy or a fair Wispr speed ranking.

Hints are capped at 192 tokenizer tokens and cached; a large vocabulary does not fit simultaneously and is not acoustic voice training. Other processes/local AI servers own their allocations; global VRAM is not reserved by this app.

Parakeet and whisper.cpp remain candidates, not functioning integrations. No speed/compatibility claim is made for them. General LLM rewriting is constrained by ordered meaning guards; local Ollama/llama.cpp availability and performance depend on a separately configured server. No mandatory Ollama or cloud account is required.
