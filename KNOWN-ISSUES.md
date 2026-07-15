# Known Issues

This workspace is an early local-first implementation. Please be aware of the following architectural limitations:

- **Local trust model:** The local HTTP service has no authentication and permissive cross-origin access. It should only be exposed on a trusted machine and loopback interface.
- **Non-transactional storage:** Metadata, files, catalogs, and bidirectional links are written separately. Crashes or concurrent operations can leave partial or inconsistent state.
- **Sync integrity:** Pull and clone are additive, non-atomic operations. Relationship metadata and file hashes may become stale or inconsistent, and downloaded content is not fully verified.
- **Large-file scalability:** Hashing, upload, download, and browser dataset parsing may buffer entire artifacts in memory.
- **Single-writer assumption:** The store assumes one workspace server, but ownership and mutual exclusion are not enforced across all operations.
- **Limited validation and recovery:** Several domain fields are loosely validated, corrupt records may be skipped during discovery, and ingest/sync recovery is largely manual.
