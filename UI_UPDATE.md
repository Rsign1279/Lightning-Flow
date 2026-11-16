# LightningFlow 0.4.0 — desktop redesign

An original interface inspired by the uncluttered organization of Wispr Flow's public desktop hub. No Wispr source, branding, protected assets or private APIs are used.

Home now combines shortcut keycaps, recording state, the latest saved transcript and recent dictations. The log groups transcripts by date, with search and nearby Copy/Open actions. Original line icons replace the text-only navigation. Everyday tools stay in the sidebar; model/microphone/shortcut/performance configuration lives under Settings. The appearance menu is in the top bar, with warm ivory/violet Light and graphite/lavender Dark themes. A new violet application icon and a smaller 294×64 recording capsule complete the visual changes.

The 120-ms hold threshold, tap no-op, immediate release cutoff, GPU residency, text-delivery guard, clipboard handling and local-log preferences are unchanged. Home restores the most recent saved nonempty transcript when it opens. No demo records are added to the user's log; the design preview used a separate, explicitly named test-data directory.

## Validation

- 90 automated tests passed.
- Actual source GUI → IPC worker → resident CUDA → scratchpad/history passed. All nine screens were constructed in both Light and Dark without callback errors. Latest replay GPU decode totaled about 74 ms and the GUI heartbeat maximum gap was 30.48 ms. This is accelerated PCM replay, not an acoustic/keyboard benchmark.
- The recording widget measured 16.10-ms median frames, 16.64-ms p95, 17.60-ms maximum, with a 49.68-ms hide transition in the isolated synthetic-level test. It did not take focus and released its timer request after hiding.
- The source dark-theme Home preview was visually inspected through Windows computer use. The user stopped Computer Use with Escape during further review; no more on-screen inputs were issued. Light theme, final navigation, log and installer were not subsequently inspected manually. Their source screens constructed successfully; automated checks do not replace full manual acceptance.
- Build/payload/source-integrity checks are recorded in the 0.4.0 package manifest. ASR and integration logic are compared byte-for-byte with the archived 0.3.1 sources.

CustomTkinter accessibility/screen-reader limits, arbitrary app compatibility limits and unsigned binaries remain. No every-frame, zero-latency, accuracy or universal-insertion guarantee is made.

Reference: [Wispr Flow's public desktop hub guide](https://docs.wisprflow.ai/articles/5096240724-navigating-the-wispr-flow-app-desktop-ios-and-android).

## 0.4.1 log performance fix

The 100-cycle test exposed a slow log-rendering path. The log now reuses ten cards with Previous/Next controls; search still covers all saved entries. New recordings refresh the existing cards instead of rebuilding the whole log. Both the original 100-cycle run and another 100-cycle verification completed without dictation failures. See TEST_100.md for the raw scopes, timings and remaining navigation costs. Audio capture, GPU inference, shortcut gestures and text insertion are unchanged.
