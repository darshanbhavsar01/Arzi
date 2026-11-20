#!/usr/bin/env bash
# Least-privilege IAM for the Cloud Run runtime service account. Bindings are idempotent.
#
#   PROJECT_ID=... bash infra/iam.sh            (BUCKET defaults to ${PROJECT_ID}-arzi-docs)
#
# Project roles:  aiplatform.user, datastore.user, logging.logWriter, cloudtrace.agent,
#                 secretmanager.secretAccessor
# Bucket role:    storage.objectAdmin on the documents bucket only (not project-wide)
# Self:           iam.serviceAccountTokenCreator, so the service can sign V4 URLs without a key
# Build:          run.builder on the default compute SA, which Cloud Build uses for
#                 `gcloud run deploy --source` in projects created after mid-2024
set -euo pipefail
source "$(dirname "$0")/lib.sh"

require_vars PROJECT_ID
BUCKET="$(bucket_name)"
SA="$(sa_email)"

for role in roles/aiplatform.user roles/datastore.user roles/logging.logWriter \
            roles/cloudtrace.agent roles/secretmanager.secretAccessor; do
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA" --role="$role" --condition=None --quiet --format=none
done

run gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA" --role="roles/storage.objectAdmin" --format=none

run gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --member="serviceAccount:$SA" --role="roles/iam.serviceAccountTokenCreator" --format=none

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || true)"
PROJECT_NUMBER="${PROJECT_NUMBER:-<PROJECT_NUMBER>}"   # unknown only when the project is new
run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/run.builder" --condition=None --quiet --format=none

echo "IAM bindings applied for $SA."
