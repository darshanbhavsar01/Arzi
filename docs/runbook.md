# Runbook

Operational commands for the Arzi deployment. Region: `asia-south1` (Mumbai). Service: `arzi`.
Every infra script accepts `DRY_RUN=1` to print the exact commands without running them.

## Variables

```bash
export PROJECT_ID=<gcp-project-id>
export BILLING_ACCOUNT=<account-the-project-is-billed-to>        # gcloud billing accounts list
export BILLING_ACCOUNT_EVENT=<event-credit-billing-account-id>   # optional; skipped if closed
export BILLING_ACCOUNT_OWNER=<owner-billing-account-id>
```

## First-time setup (owner)

```bash
gcloud auth login && gcloud auth application-default login
bash infra/bootstrap.sh     # billing link (skipped if already correct), APIs, Firestore, bucket, SA, IAM
bash infra/budgets.sh       # budget alerts on each open billing account, 25/50/90/100%
npx firebase-tools@latest projects:addfirebase "$PROJECT_ID"
npx firebase-tools@latest deploy --only firestore --project "$PROJECT_ID" --config infra/firebase.json  # deny-all rules
GOOGLE_CLOUD_PROJECT="$PROJECT_ID" make models   # pick model IDs, record them in docs/PROGRESS.md
make deploy
```

Email/Password and Google sign-in providers are enabled in the Console (Authentication →
Sign-in method) when Phase 7 turns on Firebase Auth.

## Deploy and rollback

```bash
make deploy                                            # asks for confirmation
gcloud run revisions list --service arzi --region asia-south1
gcloud run services update-traffic arzi --region asia-south1 --to-revisions <REVISION>=100
```

## Spend kill switches

Budgets **alert**; they do not cap spend. To stop spend immediately:

```bash
# 1. Stop all model spend: serve recorded responses instead of calling Gemini.
gcloud run services update arzi --region asia-south1 --update-env-vars ARZI_LLM_MODE=replay
# 2. Limit concurrency of everything else.
gcloud run services update arzi --region asia-south1 --max-instances=1
```

The in-app budget guard (Phase 3) also refuses live LLM calls once `ARZI_DAILY_BUDGET_INR`
(default ₹150) is reached for the day.

## Billing switch (owner action)

Before the event credit expires (confirm the exact expiry under Billing → Credits):

```bash
make billing-switch    # asks you to type "switch"; re-links to BILLING_ACCOUNT_OWNER and verifies
```

## Pitch window

```bash
gcloud run services update arzi --region asia-south1 --min-instances=1   # warm, before the pitch
gcloud run services update arzi --region asia-south1 --min-instances=0   # revert right after
```

## LLM mode flip

The live link runs `hybrid`: the demo cases are served from recorded Gemini responses (free,
instant) and any other document goes to Vertex AI behind the daily budget guard
(`ARZI_DAILY_BUDGET_INR`, ₹100; prices from `ARZI_PRICE_TABLE_JSON`, passed by `make deploy`).
Modes: `replay` (never spends), `hybrid`, `live` (everything live). To switch:

```bash
gcloud run services update arzi --region asia-south1 --update-env-vars ARZI_LLM_MODE=replay   # stop all model spend
gcloud run services update arzi --region asia-south1 --update-env-vars ARZI_LLM_MODE=hybrid   # back
```

## Smoke test after a deploy

```bash
curl -fsS https://arzi-<hash>.a.run.app/health
curl -fsS https://arzi-<hash>.a.run.app/readyz
```

Then run the demo script in `docs/demo-script.md` once on a laptop and once on a phone.

## Health

- `GET /healthz` — liveness for Cloud Run probes; no dependencies. On the public `*.run.app` URL
  Google's front end reserves this path (returns its own 404), so external checks use `GET /health`.
- `GET /readyz` — Firestore and Cloud Storage reachability with the runtime identity; 503 if
  either fails (the body names the failing check and the exception type only).
