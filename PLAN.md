# Vertical slice scope

1. Inspect OpenWhispr and Yap licenses, capture, warm inference and insertion.
2. Implement original console application: registered global toggle -> on-demand microphone -> bounded audio segments -> resident CUDA ASR -> guarded Unicode input.
3. Run unit tests, real microphone probe, native edit-control input/hotkey tests, and offline synthetic speech benchmark on this RTX 5070.
4. Deliver runnable source, setup/launch scripts and measured results. No GUI, LLM, installer or product-wide feature work in this slice.

Done requires real CUDA execution, no silent CPU fallback, failure recovery, and measured latency with limitations stated. Other running GPU applications must not be terminated or unloaded.
