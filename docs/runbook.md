# Runbook

Operational commands for the Arzi deployment. Region: `asia-south1` (Mumbai). Service: `arzi`.
Every infra script accepts `DRY_RUN=1` to print the exact commands without running them.

## Variables

```bash
export PROJECT_ID=<gcp-project-id>
export BILLING_ACCOUNT_EVENT=<event-credit-billing-account-id>   # gcloud billing accounts list
export BILLING_ACCOUNT_OWNER=<owner-billing-account-id>
```

## First-time setup (owner)

```bash
gcloud auth login && gcloud auth application-default login
bash infra/bootstrap.sh     # project, billing link (event account), APIs, Firestore, bucket, SA, IAM
bash infra/budgets.sh       # budget alerts on both billing accounts, 25/50/90/100%
firebase projects:addfirebase "$PROJECT_ID"
firebase deploy --only firestore --project "$PROJECT_ID" --config infra/firebase.json  # deny-all rules
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

## Health

- `GET /healthz` — liveness; no dependencies.
- `GET /readyz` — Firestore and Cloud Storage reachability with the runtime identity; 503 if
  either fails (the body names the failing check and the exception type only).
