#!/usr/bin/env bash
# Deploy Nawa Copilot to Azure Container Apps (scale-to-zero). Run in Azure Cloud Shell (Bash):
#
#   git clone https://github.com/pornpojmundee/enterprise-copilot && cd enterprise-copilot
#   bash scripts/azure/deploy_containerapp.sh
#
# Creates (in the existing resource group, Sweden Central):
#   cae-entcopilot-dev-swc  Container Apps environment (Consumption, no Log Analytics workspace)
#   ca-entcopilot-dev-swc   Container App: app container + Postgres sidecar, 0..1 replicas
# and gives the app's managed identity the "Cognitive Services OpenAI User" role on the existing
# Azure OpenAI resource — no API key is stored anywhere.
# Idle cost: 0 (scales to zero). Active: ~2.5 vCPU / 5 GiB while a replica runs, covered by the
# monthly Container Apps free grant for a demo's usage. Re-running the script updates the app.
set -euo pipefail

RG=${RG:-rg-entcopilot-dev-swc}
LOC=${LOC:-swedencentral}
ENV_NAME=${ENV_NAME:-cae-entcopilot-dev-swc}
APP=${APP:-ca-entcopilot-dev-swc}
OAI=${OAI:-oai-entcopilot-dev-swc}
MODEL_DEPLOYMENT=${MODEL_DEPLOYMENT:-gpt-5-mini}
IMAGE=${IMAGE:-ghcr.io/pornpojmundee/enterprise-copilot:latest}
DAILY_BUDGET_USD=${DAILY_BUDGET_USD:-0.5}

echo "== checks"
az account show --query "{subscription:name, user:user.name}" -o table
az group show -n "$RG" --query name -o tsv >/dev/null
OAI_ID=$(az cognitiveservices account show -n "$OAI" -g "$RG" --query id -o tsv)
OAI_ENDPOINT=$(az cognitiveservices account show -n "$OAI" -g "$RG" --query properties.endpoint -o tsv)
LLM_BASE_URL="${OAI_ENDPOINT%/}/openai/v1/"

echo "== providers + CLI extension (first time only)"
az extension add --name containerapp --upgrade --only-show-errors -y
az provider register -n Microsoft.App --wait

echo "== environment $ENV_NAME"
if ! az containerapp env show -n "$ENV_NAME" -g "$RG" -o none 2>/dev/null; then
  az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOC" --logs-destination none -o none
fi
ENV_ID=$(az containerapp env show -n "$ENV_NAME" -g "$RG" --query id -o tsv)

# Secrets are generated here and go straight into the Container App — never printed.
# On an update, keep the existing ones so the database password and sign-in tokens stay valid.
if az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
  DB_PASSWORD=$(az containerapp secret show -n "$APP" -g "$RG" --secret-name db-password --query value -o tsv)
  API_SECRET=$(az containerapp secret show -n "$APP" -g "$RG" --secret-name api-secret --query value -o tsv)
else
  DB_PASSWORD=$(openssl rand -hex 24)
  API_SECRET=$(openssl rand -hex 32)
fi

YAML=$(mktemp --suffix .yaml)
trap 'rm -f "$YAML"' EXIT
cat > "$YAML" <<YAML
location: $LOC
identity:
  type: SystemAssigned
properties:
  environmentId: $ENV_ID
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: 8000
      transport: auto
      allowInsecure: false
    secrets:
      - name: db-password
        value: "$DB_PASSWORD"
      - name: api-secret
        value: "$API_SECRET"
  template:
    scale:
      minReplicas: 0
      maxReplicas: 1
      rules:
        - name: http
          http:
            metadata:
              concurrentRequests: "20"
    containers:
      - name: app
        image: $IMAGE
        resources: { cpu: 2.0, memory: 4Gi }
        env:
          - { name: LLM_AUTH, value: entra }
          - { name: LLM_BASE_URL, value: "$LLM_BASE_URL" }
          - { name: LLM_CHAT_MODEL, value: "$MODEL_DEPLOYMENT" }
          - { name: POSTGRES_HOST, value: localhost }
          - { name: POSTGRES_PORT, value: "5432" }
          - { name: POSTGRES_DB, value: copilot }
          - { name: POSTGRES_USER, value: copilot }
          - { name: POSTGRES_PASSWORD, secretRef: db-password }
          - { name: API_SECRET_KEY, secretRef: api-secret }
          - { name: DAILY_LLM_BUDGET_USD, value: "$DAILY_BUDGET_USD" }
          - { name: RATE_LIMIT_PER_MIN, value: "8" }
        probes:
          - type: Startup
            httpGet: { path: /healthz, port: 8000 }
            initialDelaySeconds: 20
            periodSeconds: 10
            failureThreshold: 30
          - type: Liveness
            httpGet: { path: /healthz, port: 8000 }
            periodSeconds: 30
      - name: db
        image: docker.io/pgvector/pgvector:pg16
        resources: { cpu: 0.5, memory: 1Gi }
        env:
          - { name: POSTGRES_DB, value: copilot }
          - { name: POSTGRES_USER, value: copilot }
          - { name: POSTGRES_PASSWORD, secretRef: db-password }
YAML

echo "== container app $APP"
if az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp update -n "$APP" -g "$RG" --yaml "$YAML" -o none
else
  az containerapp create -n "$APP" -g "$RG" --yaml "$YAML" -o none
fi

echo "== managed identity -> Azure OpenAI (keyless)"
PRINCIPAL=$(az containerapp show -n "$APP" -g "$RG" --query identity.principalId -o tsv)
az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" --scope "$OAI_ID" -o none 2>/dev/null || echo "(role already assigned)"

FQDN=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo
echo "Done: https://$FQDN"
echo "First visit after idle wakes the app (about 2-3 minutes: database seed + model load). Refresh if it times out."
echo "Role assignments can take a few minutes to apply; the first question may fail with 401 until then."
