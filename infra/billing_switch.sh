#!/usr/bin/env bash
# Move the project from the event credit billing account to the owner's account.
# Owner action only (before the event credit expires). Run via `make billing-switch`.
#
#   PROJECT_ID=... BILLING_ACCOUNT_OWNER=... make billing-switch
set -euo pipefail
source "$(dirname "$0")/lib.sh"

require_vars PROJECT_ID BILLING_ACCOUNT_OWNER

if ! is_dry_run; then
  echo "Current billing for $PROJECT_ID:"
  gcloud billing projects describe "$PROJECT_ID" --format='table(billingAccountName,billingEnabled)'
fi
confirm "This re-links $PROJECT_ID to billing account $BILLING_ACCOUNT_OWNER. Charges after this point go to that account." "switch"

run gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_OWNER"
run gcloud billing projects describe "$PROJECT_ID"
echo "Check that billingEnabled is True and billingAccountName ends with $BILLING_ACCOUNT_OWNER."
