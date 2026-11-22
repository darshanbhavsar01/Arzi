# Privacy and data protection

How Arzi handles personal data under India's Digital Personal Data Protection Act, 2023 (DPDP).
All data in this repository and in every demo is synthetic; hospitals and insurers are fictional.

## What is collected and why

| Data | Where it comes from | Purpose |
|---|---|---|
| Claim documents (bill, policy, discharge summary, reports, insurer letters) | Uploaded by the hospital desk, or by a family through the free check | Audit the claim and draft an appeal |
| Extracted facts (bill lines, dates, policy terms) | Gemini extraction of those documents | Rules engine input |
| Patient identifiers (name, phone, Aadhaar-like and PAN-like numbers, email, policy and member numbers, address) | Extraction | Only to address a signed appeal letter |
| Consent record (who gave it, for what purpose, when) | Desk, before any processing | Lawful basis and accountability |
| Audit log (who did what, when) | Every action | Accountability |

## How it flows

1. **Consent first.** An audit cannot start until consent is recorded on the claim
   (`consent-required` problem otherwise).
2. **Redaction before reasoning.** Right after extraction, every identifier is replaced by a stable
   pseudonym (`P-7F3A`, an HMAC with a deployment secret). Every later step (policy interpreter,
   flag explainer, appeal drafter, family explainer, narration) sees pseudonyms only.
3. **Restricted vault.** Raw values live in a separate `restricted/identity` document per claim,
   read only to address a letter that a named reviewer has signed.
4. **Family links** store only the SHA-256 of the token; the token is shown once, expires (7 days by
   default) and can be withdrawn. `Referrer-Policy: no-referrer` keeps it from leaking to other
   sites, and the log filter removes it from access-log paths.

## Where it is stored

Firestore and Cloud Storage in `asia-south1` (Mumbai). Gemini calls go to Vertex AI; the global
endpoint processes prompts transiently and stores nothing at rest outside Mumbai. The documents
bucket uses uniform access with public access prevention enforced.

## Logs

Logs are structured JSON (Cloud Logging), correlated to the request trace. A filter on the only log
handler scrubs emails, phone numbers, Aadhaar-like and PAN-like numbers and family-link tokens from
every line, including exception text and access-log paths, before anything is written
(`arzi/observability/logging.py`, tested). Problem responses never echo document text.

## Data principal rights

| Right | How | Who |
|---|---|---|
| Access | `GET /api/v1/claims/{id}/export`: the claim record, documents (metadata and hashes), runs, appeals, audit log and how many family links exist. Raw identifiers are not exported, only which pseudonyms have a value | Any signed-in desk user of that hospital; the export is itself logged |
| Erasure | `DELETE /api/v1/claims/{id}`: the claim, every subcollection (documents, runs, audit log, identity vault, appeals), its family links and every stored object (uploads, narrated audio) | Administrators only; cannot be undone |
| Correction | Bill lines are corrected in the workspace (`PATCH .../lines/{line}`), and the engine re-runs | Desk |

## Retention

- `POST /api/v1/admin/retention` (administrators) erases every claim of the hospital not updated in
  `ARZI_RETENTION_DAYS` (default 30). Run it daily from Cloud Scheduler with an OIDC token; the job
  is optional and not provisioned for the event build.
- The Cloud Storage lifecycle rule also deletes uploads after 30 days as a backstop.

## Tenancy

Every repository call takes the hospital ID from the authenticated principal, and paths are
`hospitals/{hid}/claims/{cid}/…`. A test calls every claim route in the API contract as another
hospital's administrator and expects 404 on each (`tests/integration/test_hardening_api.py`).
