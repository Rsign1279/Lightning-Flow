# Private kernel-report access

Double-click `scripts/Export-TdrDump.vbs` and approve the Windows UAC prompt for PowerShell. The one-time elevated helper reads only `WATCHDOG-20261115-2254.dmp`, the report named in the original NVIDIA-reset incident's Windows Error Reporting event. It copies the report into this checkout's ignored `.work/kernel-diagnostics` folder and verifies the copy with SHA-256. `status.json` records success or an understandable error.

The helper does not change source permissions, take ownership, alter drivers/clocks/TDR settings, enable a crash, upload data or modify dictation behavior. PowerShell's execution-policy bypass applies only to this helper process. You do not need to run Codex as administrator or grant access to all of Windows.

Kernel memory reports can contain private data. They stay local and must not be committed or uploaded to GitHub. Only a redacted diagnosis and any verified source fix should be published.

If double-click is unavailable, open **PowerShell as administrator**, then run this from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Export-TdrDump.ps1
```

If Windows says the report does not exist, collection has not succeeded; do not create an unrelated live dump and assume it represents the past incident. Existing kernel reports are stored by default under [Windows LiveKernelReports](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/kernel-live-dump-code-reference). Creating a dump now cannot recreate the state at the original timeout.

## Investigation result: November 16, 2026

The original incident's protected report was successfully exported locally, with matching source/copy SHA-256. The copied live kernel dump is 3,649,031 bytes. No dump, raw event log or full Windows Error Reporting report is published.

The Microsoft debugger, with matching Microsoft public symbols, confirms `VIDEO_TDR_TIMEOUT_DETECTED (0x117)`. Its second parameter points into `nvlddmkm.sys`, version 32.0.16.1088 (NVIDIA 610.88). The installed driver file also passes Windows Authenticode verification; that is an integrity/signature result, not proof of a bug-free driver. The capture stack runs through `dxgmms2!VidSchiReportHwHang` and `dxgkrnl!TdrCollectDbgInfoStage1`. The `System` process here is the scheduler/capture context; it does not identify the application that submitted the stalled work.

The original WER report labels the incident `LKD_0x117_Tdr:A_IMAGE_nvlddmkm.sys_Blackwell_UserOC`. This is an investigative clue, **not proof that an overclock caused the timeout**. Read-only NVML `nvmlDeviceGetClockOffsets` queries subsequently returned zero graphics and memory offsets in P0, P2 and P8. The local NVIDIA tuning database contained no GPU-error or OC-scanner result rows. These later observations cannot establish the clock state at the incident. Legacy unsupported offset queries were not treated as zero.

Local `!analyze -v` reports `LKD_0x117_ANALYSIS_INCONCLUSIVE!unknown_function`. NVIDIA private symbols and a decoder for its secondary dump data are unavailable here. `.enumtag` confirms a secondary data block; its undocumented bytes are not evidence of a particular clock fault. Public symbols did not resolve the internal TDR context type. The available dump does not establish whether the original trigger was a driver defect, unstable hardware/tuning, or an interaction with another GPU workload.

The separate application dump identifies a later CTranslate2 CUDA allocator cleanup exception terminating Python. Version 0.6.1 already contains that native failure in an owned GPU child, retains capture/text, and prevents incomplete insertion. Containment does not repair a display driver or prove the original timeout cannot recur.

No driver upgrade, TDR timeout change, GPU clock/power change, allocator switch, model/precision reduction or shortcut change was made in this investigation. The original cause remains unresolved; calling this a verified driver fix would be inaccurate. The strongest next evidence would be a vendor interpretation of the existing private NVIDIA data, or a reproducible failure captured with pre-fault GPU/ETW diagnostics. A later successful benchmark alone cannot prove causation.

### Reproducing the local analysis

Use an official Microsoft debugger. Keep the dump and symbol cache outside tracked source. Open only the copied incident dump. A symbol server request downloads matching symbols; it does not upload the memory dump.

```text
.sympath srv*C:\private-symbol-cache*https://msdl.microsoft.com/download/symbols
.reload /f nt
!analyze -v
kn
lmvm nvlddmkm
.enumtag
```

Microsoft documents [0x117 and its parameters](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x117---video-tdr-timeout-detected) and [secondary callback data](https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/-enumtag--enumerate-secondary-callback-data-). NVIDIA documents the read-only [clock-offset structure](https://docs.nvidia.com/deploy/nvml-api/latest/api/structnvmlClockOffset__v1__t.html). Never infer historical tuning solely from current readings or interpret normal boost clocks as proof of a user overclock.

## Fresh regression verification

The November 16 audit passed 295 automated tests and built the source wheel. Actual RTX 5070 CUDA replay passed 100 hold-to-talk and 100 hands-free cycles with one model initialization, 200 persistent log records and zero audio appends after stop. The five terms in the public example vocabulary were checked; this is not a published test of the user's private knowledge bank.

Both long cases processed 30 minutes of synthetic audio, replayed faster than real time. Their 27,014-character transcripts matched the prior verified release run exactly, including the final spoken marker, with unchanged fixture WER. Every stream closed and delivered audio was released. No TDR events were observed during the complete audit window. Separate own-child exit tests verified retained audio/text in both modes; direct/isolated decoding matched on 32 actual CUDA decodes.

Median stop-to-result was 160.4 ms for hold and 159.8 ms for hands-free in the short-cycle replay; p95 was 273.2/323.8 ms, with maxima 760.7/517.5 ms. These are measured replay results under the observed machine load, not a guaranteed latency or evidence that a diagnostic-only commit made inference faster. Physical global-hook behavior, human speech and external-editor insertion were not exercised in this audit.

Evidence: [audit summary](results/kernel-audit-2026-11-16.json), [200-cycle results](results/ctrl-win-kernel-audit-2026-11-16.json), [GPU fault/parity results](results/gpu-isolation-kernel-audit-2026-11-16.json), and [long recordings](results/long-recordings-kernel-audit-2026-11-16.json). The unchanged decoder, model and precision preserve the tested recognition behavior; a successful run does not identify or cure the original NVIDIA timeout.
