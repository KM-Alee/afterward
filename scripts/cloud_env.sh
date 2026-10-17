#!/usr/bin/env bash
# Copy the settings the cloud app needs from .env to the Alternate Clouds service.
# Prints setting NAMES only, never values. Run it yourself:  bash scripts/cloud_env.sh
# Skips DATABASE_URL (the cloud links its own database) and PUBLIC_BASE_URL (cloud URL differs).
#
#   bash scripts/cloud_env.sh                      copy settings to afterward-app
#   bash scripts/cloud_env.sh --webhook https://…  also point Telegram at that public URL
set -euo pipefail
cd "$(dirname "$0")/.."
SERVICE="afterward-app"
WEBHOOK_URL=""
if [[ "${1:-}" == "--webhook" ]]; then WEBHOOK_URL="${2:?give the public https URL}"; fi

KEYS=(
  OPENAI_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET
  GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET GOOGLE_REFRESH_TOKEN_FAMILY GOOGLE_REFRESH_TOKEN_PROVIDERS
  VAULT_KEY DEMO_PASSCODE FAMILY_MAILBOX PROVIDERS_MAILBOX
  STT_MODEL LLM_FAST_MODEL LLM_ACCURATE_MODEL TTS_MODEL LLM_FAST_EFFORT LLM_ACCURATE_EFFORT
  TTS_VOICE REALTIME_MODEL REALTIME_TRANSCRIBE_MODEL REALTIME_VOICE REALTIME_SILENCE_MS
)

declare -A VALUES=()
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line#export }"
  [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
  key="${line%%=*}"; key="${key// /}"
  value="${line#*=}"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then value="${value:1:${#value}-2}"; fi
  VALUES["$key"]="$value"
done < .env

if [[ -z "$WEBHOOK_URL" ]]; then
  for key in "${KEYS[@]}"; do
    value="${VALUES[$key]:-}"
    if [[ -z "$value" ]]; then echo "  -  $key (not in .env, left as the app default)"; continue; fi
    if acc services env set "$SERVICE" "$key" "$value" >/dev/null 2>&1; then
      echo "  ✓  $key"
    else
      echo "  ✗  $key (acc refused; nothing printed)"
    fi
  done
  echo "Done. Values were copied, not shown."
  exit 0
fi

# Telegram: point the bot at the cloud app. Uses the same webhook secret.
token="${VALUES[TELEGRAM_BOT_TOKEN]:-}"
secret="${VALUES[TELEGRAM_WEBHOOK_SECRET]:-}"
[[ -z "$token" || -z "$secret" ]] && { echo "Telegram token or secret missing in .env"; exit 1; }
answer=$(curl -s "https://api.telegram.org/bot${token}/setWebhook" \
  --data-urlencode "url=${WEBHOOK_URL%/}/webhooks/telegram" \
  --data-urlencode "secret_token=${secret}" \
  --data-urlencode 'allowed_updates=["message","callback_query"]')
if [[ "$answer" == *'"ok":true'* ]]; then echo "Telegram now points at ${WEBHOOK_URL%/}/webhooks/telegram"; else echo "Telegram refused the webhook."; fi
