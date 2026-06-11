# HumanSeeker Threat Model

This document captures the threats HumanSeeker is designed to detect, the threats it explicitly does **not** address, the assumptions it relies on, and the limitations a defender should account for before deploying it.

It follows a lightweight STRIDE-style approach focused on the realistic deployment context: a local desktop application running on a single user's machine.

---

## 1. System under consideration

HumanSeeker is a desktop application that:

- Captures **behavioral telemetry** in the browser (mouse, keystroke timing, click, scroll patterns) via a JavaScript tracker
- Sends telemetry to a **local Flask backend** over loopback (127.0.0.1) only
- Builds a per-user behavioral **baseline** using exponential moving averages
- Scores new sessions against the baseline using **z-score normalization** across eight features
- Classifies sessions as **Low / Medium / High risk** using a weighted heuristic classifier
- Logs structured **detection events** to disk in JSON Lines format

The threat surface is therefore: a local Flask server bound to 127.0.0.1, a browser-side JavaScript tracker, and local JSON storage of baselines and logs.

---

## 2. Threats HumanSeeker is designed to detect

### T1. Credential-based account takeover (ATO)

An attacker who has acquired valid credentials (phishing, credential stuffing, leak dump) attempts to use a legitimate user's account. **HumanSeeker detects the behavioral divergence** between the attacker and the legitimate user because keystroke timing, mouse dynamics, click cadence, and scroll patterns are individually distinctive.

This addresses the most common modern attack class: valid-credential abuse.

### T2. Session token theft / MFA bypass via session hijacking

An attacker steals a post-authentication session token via phishing kit, infostealer malware, or man-in-the-middle. Because the token is valid, MFA does not re-trigger. **HumanSeeker treats behavioral signature as a continuous soft factor** that catches anomalies after the front-door check has passed.

### T3. Insider abuse on a shared workstation

A second person using an already-authenticated workstation behaves differently than the registered user. **HumanSeeker flags the deviation** without requiring re-authentication.

### T4. Bot / automated abuse mimicking human input

Crude bots and automation tools generate inputs that have unnaturally low timing variance, uniform mouse velocity, or geometrically perfect paths. **HumanSeeker's variance and curvature features detect these signatures.**

---

## 3. Threats HumanSeeker explicitly does NOT address

It is important to be honest about scope. HumanSeeker does not protect against:

| Threat | Why not | Appropriate control |
|---|---|---|
| Initial credential theft (phishing) | HumanSeeker activates after login | Email security, user awareness training, FIDO2 |
| Malware on the endpoint | Behavioral telemetry can be tampered with by privileged malware | EDR, antivirus, application allowlisting |
| Network-level attacks (MitM, BGP hijack) | Out of scope for a behavioral layer | TLS, certificate pinning, network segmentation |
| Vulnerabilities in target applications | Behavioral biometrics doesn't replace AppSec | SAST, DAST, secure SDLC |
| Sophisticated mimicry attacks (e.g. an attacker trained on captured behavior) | Theoretical, requires extensive surveillance of victim | Hardware-backed authentication, anomaly fusion |
| Insider with full administrative privilege | Such an actor can disable the agent | Privileged access management, separation of duty |
| Ransomware payload execution | Post-execution detection is the wrong layer | Backups, EDR, network segmentation |

---

## 4. Trust boundaries and attack surface

```
+--------------------------------------------------------------------+
|                       USER'S OPERATING SYSTEM                      |
|                                                                    |
|  +----------------------+         +------------------------------+ |
|  |  Browser (frontend)  | ----->  | Flask backend (127.0.0.1)    | |
|  |  - tracker.js        |  HTTP   | - /session, /latest, /api/*  | |
|  |  - dashboard.html    |         | - classifier, scorer         | |
|  +----------------------+         +-------+----------------------+ |
|                                            |                       |
|                                            v                       |
|                                   +------------------+             |
|                                   | Local JSON store |             |
|                                   | - baselines/     |             |
|                                   | - logs/          |             |
|                                   +------------------+             |
+--------------------------------------------------------------------+
```

**Trust boundaries:**

1. **Browser → Backend.** Loopback only. Input is treated as untrusted, validated, rate-limited, and bounded in size before processing.
2. **Backend → Disk.** Baselines and logs are written to per-user files. Filenames are derived from a validated character set (`[A-Za-z0-9_.-]`) to prevent path traversal.
3. **Backend → Network.** **Zero.** HumanSeeker makes no outbound network calls and has no external API dependencies. This is a deliberate design choice for privacy and air-gap deployment.

---

## 5. Assumptions

The threat model assumes:

- The operating system kernel and the user's account are not already compromised at the privilege level that would let an attacker tamper with HumanSeeker's process memory.
- The browser is reasonably modern and respects the same-origin policy and the Content-Security-Policy headers issued by the backend.
- The user does in fact use the workstation regularly enough to establish a useful behavioral baseline (a minimum of three sessions before scoring begins).

When any of these assumptions does not hold, behavioral biometrics is not the right control.

---

## 6. STRIDE summary

| Category | Threats | Mitigations in HumanSeeker |
|---|---|---|
| **Spoofing** | Attacker impersonates legitimate user with stolen credentials | Behavioral baseline divergence (T1, T2) |
| **Tampering** | Malicious browser script alters telemetry | Input validation, length caps, CSP, rate limiting |
| **Repudiation** | User denies action; need an audit trail | Structured JSON detection event log (logs/detections.jsonl) with ISO timestamps |
| **Information Disclosure** | Leak of behavioral data | Offline operation, no telemetry leaves device, no keystroke content captured (only timing) |
| **Denial of Service** | Flooding /session with payloads | Per-user rate limiting, hard caps on event count per session, payload size limits |
| **Elevation of Privilege** | Out of scope (single-user desktop app) | OS-level controls |

---

## 7. Privacy posture

HumanSeeker is privacy-aware by design:

- **No keystroke content is captured.** Only timing (dwell, flight) and a non-content key category. Passwords, messages, and content typed are never observed.
- **No telemetry leaves the device.** No outbound HTTP, no telemetry pipeline, no usage analytics. All state lives in local JSON files the user controls.
- **No user identity beyond a self-chosen `user_id` string.** No email, no device fingerprinting, no third-party identifiers.
- **Logs are local.** Detection events go to `logs/detections.jsonl` and security events to `logs/security.jsonl`. Both are plain JSON Lines, readable and deletable by the user.

This posture makes HumanSeeker deployable in air-gapped or regulated environments where data exfiltration is unacceptable.

---

## 8. Known limitations

- **Cold start.** The first three sessions are baseline-learning only and do not produce a risk classification. During this window, the user has no behavioral protection.
- **Behavioral drift.** Genuine changes in user behavior (new keyboard, injury, fatigue) will produce false positives. The EMA baseline adapts, but recently changed behavior may flag for several sessions.
- **False positive rate has not been formally benchmarked.** A production deployment should run synthetic adversarial and legitimate-drift sessions to characterize FPR before relying on the classifier in a high-stakes context.
- **Single-user scope.** The current design is per-user-per-workstation. Multi-user enterprise rollout would require account federation and centralized policy management, which are not implemented.
- **Heuristic classifier.** Classification is rule-based, not learned. Rule weights were chosen for interpretability and may not be optimal for every user population.
