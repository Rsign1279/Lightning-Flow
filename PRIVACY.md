# Privacy

No mandatory account, telemetry, automatic audio upload or cloud transcription. The microphone opens only for an explicit recording/microphone test. Installed speech models run locally on CUDA. Successful recordings normally discard audio; failed recordings retain up to five audio buffers in process memory for explicit local export or GPU retranscription.

Encrypted failed-recording recovery is a separate opt-in, off by default. Completed, undelivered recordings are saved in exact float32 chunks with Windows-user DPAPI protection, capped at five recordings and 1 GiB on disk. The app reports eviction and storage failures. Restart can recover committed recordings without enabling transcript history. Turning recovery off or clearing history requests deletion. A save interrupted before its manifest commits is not recoverable; live microphone capture is not crash-journaled. Unexpected process termination can still lose unfinished or uncommitted audio. Retranscription uses the resident CUDA model, updates the log for review and never automatically pastes the recovered recording.

New profiles leave history off. If enabled, at most 200 entries are retained. Settings/profile and transcript payloads are protected with Windows DPAPI for the current Windows user. Legacy history is migrated when the new version opens it; existing external exports/backups remain as they were. DPAPI protects data at rest and does not protect against malware acting as your signed-in user, live process inspection, or compromise of the OS. Some metadata such as filenames/database row IDs remains visible.

Text/profile/audio exports are explicit plaintext files at the location you choose. Keep them out of public repositories. Clear History removes saved rows and tells the worker to forget retained recovery audio. Model files and runtime paths are not transcript content and are not encrypted by this feature.

Optional AI accepts loopback Ollama or llama.cpp endpoints only. HTTP proxy settings and redirects are disabled for transcript requests. Remote/cloud Ollama model metadata is refused. The operator must still trust their local server and its configuration; the app cannot certify third-party server behavior.

Network requests occur for explicitly requested dependency/model setup and model publisher metadata, for configured local AI, or for a manual/opt-in GitHub release check. Startup release checks are off by default; a check sends a normal HTTPS request to GitHub with a generic user agent, no audio/profile/transcript payload. Clicking Releases opens the public repository in your browser. No installer runs automatically.

Temporary paste sets Windows clipboard-history/cloud-sync exclusion markers. The previous clipboard is restored only if the user has not copied something new. Unsupported clipboard formats use the alternate delivery path; restoration can still be blocked and is reported. Focus/readback verification reads the target locally and is not sent to a cloud service.

Source publication excludes personal profiles, histories, recordings, recovery files, local runtime manifests, credentials, model downloads and environments. The example vocabulary and benchmark recording are synthetic/public project fixtures.
