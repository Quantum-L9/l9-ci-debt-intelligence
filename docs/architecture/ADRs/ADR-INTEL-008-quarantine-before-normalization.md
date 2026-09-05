# ADR-INTEL-008: Sensitive events are quarantined before corpus inclusion
- Status: Accepted
- Phase: INTEL-P1
## Decision
Events containing suspected credentials, private keys, authorization headers,
absolute local paths, or explicitly unredacted payloads are quarantined.
Quarantine preserves the event hash and limitations but creates no accepted
corpus record.
The ingestion service does not fabricate redacted replacements.
Historical provider material is screened before historical normalization.
Unsafe historical material is represented only by its content digest and
limitations in historical quarantine state; raw logs never enter corpus,
snapshots, defense packs, or a synthetic redacted replacement.
