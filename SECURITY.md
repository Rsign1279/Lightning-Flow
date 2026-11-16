# Security policy

Report security problems through this repository's private vulnerability reporting when available. Do not attach private dictation, credentials or personal vocabulary to public issues. For ordinary bugs, use a redacted, minimal reproduction.

Security boundaries: local-files-only CUDA inference; explicit model downloads pinned to a Hub commit and checked against publisher-hosted LFS SHA-256/Git metadata; Windows-user DPAPI storage; loopback-only optional AI; bounded queues/documents; changed-focus refusal; no blind delivery retry; no automatic installer execution.

These are engineering controls, not a security certification. Publisher-hosted hashes do not constitute independent signatures. DPAPI does not defend against a compromised signed-in account. Third-party dependencies, drivers and local model servers remain trust boundaries. UI Automation and cross-process input are not atomic; uncertain insertion is reported and retained for inspection.

Current binaries are unsigned. A trusted signing certificate/private key is not included and must not be committed. No SOC 2, ISO or HIPAA certification is claimed. See LICENSE_NOTICES.md for external proprietary NVIDIA runtime prerequisites and open-source dependency licenses.
