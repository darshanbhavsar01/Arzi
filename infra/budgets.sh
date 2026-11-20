#!/usr/bin/env bash
# Budget alerts on BOTH billing accounts, filtered to this project, at 25/50/90/100%.
# Idempotent: an existing budget with the same display name is left alone.
#
#   PROJECT_ID=... BILLING_ACCOUNT_EVENT=... BILLING_ACCOUNT_OWNER=... bash infra/budgets.sh
#
# Amounts carry their currency, which must match the billing account's currency:
#   BUDGET_EVENT_AMOUNT (default 5USD)   BUDGET_OWNER_AMOUNT (default 500INR)
#
# Budgets ALERT; they do not cap spend. Kill switches are in docs/runbook.md.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

require_vars PROJECT_ID BILLING_ACCOUNT_EVENT BILLING_ACCOUNT_OWNER
BUDGET_EVENT_AMOUNT="${BUDGET_EVENT_AMOUNT:-5USD}"
BUDGET_OWNER_AMOUNT="${BUDGET_OWNER_AMOUNT:-500INR}"

create_budget() {
  local account="$1" amount="$2" display_name="$3"

  if ! is_dry_run; then
    local account_currency="${amount: -3}" actual
    actual="$(gcloud billing accounts describe "$account" --format='value(currencyCode)')"
    if [ -n "$actual" ] && [ "$actual" != "$account_currency" ]; then
      echo "error: $display_name amount $amount is in $account_currency but account $account bills in $actual." >&2
      echo "       Set the amount in $actual, e.g. BUDGET_..._AMOUNT=<n>$actual" >&2
      exit 2
    fi
    if [ -n "$(gcloud billing budgets list --billing-account="$account" \
        --filter="displayName=$display_name" --format='value(name)')" ]; then
      echo "Budget $display_name already exists on $account; leaving it unchanged."
      return
    fi
  fi

  run gcloud billing budgets create --billing-account="$account" \
    --display-name="$display_name" --budget-amount="$amount" \
    --filter-projects="projects/$PROJECT_ID" \
    --threshold-rule=percent=0.25 --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
}

create_budget "$BILLING_ACCOUNT_EVENT" "$BUDGET_EVENT_AMOUNT" "arzi-cap-event"
create_budget "$BILLING_ACCOUNT_OWNER" "$BUDGET_OWNER_AMOUNT" "arzi-cap-owner"

echo "Verify: gcloud billing budgets list --billing-account=<ACCOUNT>"
