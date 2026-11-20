#!/usr/bin/env bash
# Build from source with Cloud Build and deploy the single `arzi` Cloud Run service.
#
#   PROJECT_ID=... make deploy
#
# Optional: ARZI_LLM_MODE (default replay until model IDs are chosen), ARZI_MODEL_FLASH,
# ARZI_MODEL_PRO, ARZI_MODEL_TTS, ARZI_MODEL_LIVE, ARZI_VERTEX_LOCATION, BUCKET.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

require_vars PROJECT_ID
BUCKET="$(bucket_name)"
LLM_MODE="${ARZI_LLM_MODE:-replay}"
BUILD_SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"

env_vars="ARZI_ENV=cloud,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ARZI_GCP_REGION=$REGION"
env_vars+=",ARZI_BUCKET=$BUCKET,ARZI_LLM_MODE=$LLM_MODE,ARZI_BUILD_SHA=$BUILD_SHA"
for name in ARZI_MODEL_FLASH ARZI_MODEL_PRO ARZI_MODEL_TTS ARZI_MODEL_LIVE ARZI_VERTEX_LOCATION; do
  if [ -n "${!name:-}" ]; then env_vars+=",$name=${!name}"; fi
done

cat <<EOF
Deploying service '$SERVICE' to $PROJECT_ID ($REGION), build $BUILD_SHA, LLM mode: $LLM_MODE.
Cost note: Cloud Build minutes, an Artifact Registry image (cleanup keeps the newest 3) and
request-based Cloud Run billing with min-instances=0 (no idle charge). Live LLM calls are
bounded by ARZI_DAILY_BUDGET_INR. Expect a few rupees per deploy.
EOF
confirm "Proceed with the deploy?" "deploy"

cd "$REPO_DIR"
run gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --source . --region "$REGION" \
  --service-account "$(sa_email)" \
  --min-instances 0 --max-instances 3 --cpu 1 --memory 1Gi --concurrency 20 --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "$env_vars"

# The source-deploy repository exists only after the first deploy; keep the newest 3 images.
run gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy \
  --project="$PROJECT_ID" --location="$REGION" \
  --policy="$INFRA_DIR/ar-cleanup.json" --no-dry-run

if ! is_dry_run; then
  url="$(gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
  echo "Service URL: $url"
  echo "Smoke test: $(curl -fsS "$url/healthz")"
fi
