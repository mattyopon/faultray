#!/bin/bash
# ステージング環境の自動セットアップ
# 使い方: ./scripts/setup-staging.sh
#
# 必要な環境変数:
#   SUPABASE_TOKEN          - Supabase Management API Token
#   STAGING_REF             - Supabase staging project ref
#   VERCEL_TOKEN            - Vercel API Token
#   VERCEL_PROJECT_ID       - Vercel Project ID
#   GITHUB_OAUTH_CLIENT_ID  - GitHub OAuth App Client ID
#   GITHUB_OAUTH_SECRET     - GitHub OAuth App Client Secret
#   GOOGLE_OAUTH_CLIENT_ID  - Google OAuth Client ID
#   GOOGLE_OAUTH_SECRET     - Google OAuth Client Secret

set -e

# Validate required env vars
for var in SUPABASE_TOKEN STAGING_REF VERCEL_TOKEN VERCEL_PROJECT_ID \
           GITHUB_OAUTH_CLIENT_ID GITHUB_OAUTH_SECRET \
           GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_SECRET; do
  if [ -z "${!var}" ]; then
    echo "ERROR: $var is not set" >&2
    exit 1
  fi
done

echo "=== FaultRay Staging Setup ==="

# 1. Supabase Auth設定
echo "1. Configuring Supabase Auth..."
curl -s -X PATCH \
  -H "Authorization: Bearer ${SUPABASE_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.supabase.com/v1/projects/${STAGING_REF}/config/auth" \
  -d "{
    \"external_github_enabled\": true,
    \"external_github_client_id\": \"${GITHUB_OAUTH_CLIENT_ID}\",
    \"external_github_secret\": \"${GITHUB_OAUTH_SECRET}\",
    \"external_google_enabled\": true,
    \"external_google_client_id\": \"${GOOGLE_OAUTH_CLIENT_ID}\",
    \"external_google_secret\": \"${GOOGLE_OAUTH_SECRET}\",
    \"site_url\": \"https://staging.faultray.com\",
    \"uri_allow_list\": \"https://staging.faultray.com/**\"
  }" > /dev/null
echo "   Done"

# 2. Vercel環境変数確認
echo "2. Checking Vercel env vars..."
curl -s -H "Authorization: Bearer ${VERCEL_TOKEN}" \
  "https://api.vercel.com/v9/projects/${VERCEL_PROJECT_ID}/env" | python3 -c "
import sys, json
d = json.load(sys.stdin)
preview_vars = [e for e in d.get('envs', []) if 'preview' in e.get('target', [])]
for e in preview_vars:
    print(f'   {e[\"key\"]} → preview')
"

# 3. IP更新
echo "3. Updating allowed IP..."
CURRENT_IP=$(curl -s --max-time 5 https://api.ipify.org)
if [ -n "$CURRENT_IP" ]; then
  curl -s -X PATCH -H "Authorization: Bearer ${VERCEL_TOKEN}" -H "Content-Type: application/json" \
    "https://api.vercel.com/v9/projects/${VERCEL_PROJECT_ID}/env/wGZbfbPjYxJzaQOI" \
    -d "{\"value\":\"${CURRENT_IP}\",\"type\":\"plain\"}" > /dev/null
  echo "   IP set to ${CURRENT_IP}"
fi

echo ""
echo "=== Setup complete ==="
echo "Staging URL: https://staging.faultray.com"
echo ""
echo "NOTE: Google OAuth redirect URI must be added manually:"
echo "  https://${STAGING_REF}.supabase.co/auth/v1/callback"
echo "  → https://console.cloud.google.com/apis/credentials"
