# Shared helpers for infra scripts. Source it; do not execute it.
#
# DRY_RUN=1 prints every mutating command instead of running it (existence checks are skipped,
# so the full sequence is shown). Use it to review exactly what a script will do.

REGION="${REGION:-asia-south1}"
SA_NAME="${SA_NAME:-arzi-run}"
SERVICE="${SERVICE:-arzi}"
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"

require_vars() {
  local missing=()
  for name in "$@"; do
    if [ -z "${!name:-}" ]; then missing+=("$name"); fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "error: set ${missing[*]} (see docs/runbook.md)" >&2
    exit 2
  fi
}

is_dry_run() { [ "${DRY_RUN:-0}" = "1" ]; }

# Print a command, then run it unless DRY_RUN=1.
run() {
  printf '+ %s\n' "$*"
  if ! is_dry_run; then "$@"; fi
}

# True when a read-only probe succeeds. In DRY_RUN it reports "absent" so creates are printed.
exists() {
  if is_dry_run; then return 1; fi
  "$@" >/dev/null 2>&1
}

# Ask the operator to type an exact word before anything that spends money or changes billing.
confirm() {
  local prompt="$1" expected="$2" answer
  if is_dry_run; then return 0; fi
  printf '%s\nType "%s" to continue: ' "$prompt" "$expected"
  read -r answer
  if [ "$answer" != "$expected" ]; then
    echo "Aborted." >&2
    exit 1
  fi
}

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$SA_NAME" "$PROJECT_ID"; }
bucket_name() { printf '%s' "${BUCKET:-${PROJECT_ID}-arzi-docs}"; }
