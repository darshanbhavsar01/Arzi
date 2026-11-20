#!/usr/bin/env bash
# One-time GCP setup for Arzi in asia-south1. Idempotent: safe to re-run.
#
#   PROJECT_ID=... BILLING_ACCOUNT_EVENT=... BILLING_ACCOUNT_OWNER=... bash infra/bootstrap.sh
#   DRY_RUN=1 PROJECT_ID=... BILLING_ACCOUNT_EVENT=... BILLING_ACCOUNT_OWNER=... bash infra/bootstrap.sh
#
# Creates the project (if missing), links the EVENT billing account, enables APIs, creates the
# Firestore database, the documents bucket (30-day lifecycle) and the runtime service account,
# then applies least-privilege IAM (infra/iam.sh). Budgets are a separate step (infra/budgets.sh).
set -euo pipefail
source "$(dirname "$0")/lib.sh"

require_vars PROJECT_ID BILLING_ACCOUNT_EVENT BILLING_ACCOUNT_OWNER
BUCKET="$(bucket_name)"

confirm "This creates resources in project $PROJECT_ID and links billing account $BILLING_ACCOUNT_EVENT." "$PROJECT_ID"

echo "== Project and billing"
if ! exists gcloud projects describe "$PROJECT_ID"; then
  run gcloud projects create "$PROJECT_ID" --name="Arzi"
fi
run gcloud config set project "$PROJECT_ID"
current_billing=""
if ! is_dry_run; then
  current_billing="$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)' 2>/dev/null || true)"
fi
if [ "$current_billing" != "billingAccounts/$BILLING_ACCOUNT_EVENT" ]; then
  run gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_EVENT"
fi
run gcloud config set run/region "$REGION"

echo "== APIs"
run gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com firestore.googleapis.com storage.googleapis.com \
  secretmanager.googleapis.com logging.googleapis.com cloudtrace.googleapis.com \
  iamcredentials.googleapis.com identitytoolkit.googleapis.com firebase.googleapis.com \
  texttospeech.googleapis.com billingbudgets.googleapis.com
# Enabled only when Phase 7 turns them on: documentai.googleapis.com dlp.googleapis.com

echo "== Firestore (Native, $REGION)"
if ! exists gcloud firestore databases describe --database="(default)"; then
  run gcloud firestore databases create --location="$REGION" --type=firestore-native
fi

echo "== Cloud Storage bucket gs://$BUCKET"
if ! exists gcloud storage buckets describe "gs://$BUCKET"; then
  run gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
run gcloud storage buckets update "gs://$BUCKET" --lifecycle-file="$INFRA_DIR/gcs-lifecycle.json"

echo "== Runtime service account $(sa_email)"
if ! exists gcloud iam service-accounts describe "$(sa_email)"; then
  run gcloud iam service-accounts create "$SA_NAME" --display-name="Arzi Cloud Run runtime"
fi

echo "== IAM (least privilege)"
PROJECT_ID="$PROJECT_ID" BUCKET="$BUCKET" bash "$INFRA_DIR/iam.sh"

cat <<EOF

Bootstrap complete. Remaining owner steps:
  1. Budgets:        PROJECT_ID=$PROJECT_ID BILLING_ACCOUNT_EVENT=$BILLING_ACCOUNT_EVENT \\
                     BILLING_ACCOUNT_OWNER=$BILLING_ACCOUNT_OWNER bash infra/budgets.sh
  2. Firebase:       firebase projects:addfirebase $PROJECT_ID
                     firebase deploy --only firestore --project $PROJECT_ID --config infra/firebase.json
                     Enable Email/Password and Google providers (Console > Authentication).
  3. Models:         GOOGLE_CLOUD_PROJECT=$PROJECT_ID make models
  4. First deploy:   PROJECT_ID=$PROJECT_ID make deploy
EOF
