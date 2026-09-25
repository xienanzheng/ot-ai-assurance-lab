# Security and scope

This is a local research simulator. It does not provide production authentication, an industrial safety case or a certified air gap. Keep live control endpoints bound to loopback and do not tunnel them to the public internet. The separately packaged public demo serves saved simulated evidence and rejects API calls.

To report a vulnerability, use GitHub's private vulnerability reporting if enabled. If it is unavailable, open an issue requesting a private reporting channel without exploit details, credentials or sensitive data. Do not test against third-party deployments without authorisation.

Reviewed memory remains untrusted context. Only an operator with local CLI/database access can approve or revoke lessons. Approval is an attestation recorded in the database, not cryptographic identity verification. The application preserves event and revision records across run resets; database administrators can still alter or delete them. Back up the database volume if retention matters.

Dependency updates and imported model weights require review. Optional external observers must remain outside control authority. Simulation operating limits are illustrative and must not be used to operate real equipment.
