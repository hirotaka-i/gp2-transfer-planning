#!/usr/bin/env bash
# Deploy the transfer-plan prototype to Cloud Run.
#   ./deploy.sh            first deploy, or redeploy after a code change
set -euo pipefail

PROJECT="gp2-release-terra"
SERVICE="gp2-release-terra"
REGION="us-central1"

gcloud config set project "$PROJECT"

# One-off: enable the APIs Cloud Run's source deploy needs.
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

# --min/max-instances 1  : Streamlit keeps session state in memory, so a second
#                          instance would strand a PI's half-filled form.
# --session-affinity     : keeps a reconnecting browser on the same instance.
# --timeout 3600         : the default 5 min would drop the WebSocket mid-form.
# --no-allow-unauthenticated : Google-account login via IAM. See below to open
#                          it up for PIs who have no Google account.
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --min-instances 1 \
  --max-instances 1 \
  --session-affinity \
  --timeout 3600 \
  --memory 1Gi \
  --cpu 1 \
  --no-allow-unauthenticated

echo
echo "Grant a colleague access with:"
echo "  gcloud run services add-iam-policy-binding $SERVICE \\"
echo "    --region $REGION --member='user:NAME@DOMAIN' --role='roles/run.invoker'"
