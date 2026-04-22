# UI Findings and Notes

## Deployment

- App is deployed to Azure Container Apps (`mlbprops-dev-ui`) in `mlbprops-dev-rg`
- Docker image is stored in ACR: `mlbpropsuiqampnp.azurecr.io/mlb-props-ui:latest`
- Container App scales to zero when idle — free when not in use, cold start takes a few seconds
- Terraform module lives in `mlb_props_infra/modules/ui/`

## Building and Pushing a New Image

Docker is not installed locally. Use ACR Tasks to build in the cloud:

```bash
cd c:/Users/Antho/Documents/mlb_props_ui
az acr build --registry mlbpropsuiqampnp --image mlb-props-ui:latest .
```

After pushing, force the Container App to pick up the new image:

```bash
az containerapp update --name mlbprops-dev-ui --resource-group mlbprops-dev-rg --image mlbpropsuiqampnp.azurecr.io/mlb-props-ui:latest
```

## Entra ID Authentication (EasyAuth)

- Auth is configured via `azapi_resource` (not `azurerm_container_app_auth_config` — that resource requires azurerm >= 3.97, we're on ~3.90)
- App Registration: `mlbprops-dev-ui-auth` in Entra ID
- Redirect URIs are managed in `terraform.tfvars` under `container_app_callback_url`

### !! Redirect URI must be updated after each redeploy

Container Apps generates a new revision suffix (e.g. `--7dpcikx`) on each deploy. EasyAuth uses the revision FQDN for the callback, not the stable app FQDN. Both are registered in `terraform.tfvars`.

**After every image push / container app update:**
1. Get the new revision FQDN:
   ```bash
   az containerapp show --name mlbprops-dev-ui --resource-group mlbprops-dev-rg --query "properties.latestRevisionFqdn" -o tsv
   ```
2. Update the revision URL in `terraform.tfvars`:
   ```
   container_app_callback_url = [
     "https://mlbprops-dev-ui.victoriousgrass-303f2d5f.eastus2.azurecontainerapps.io/.auth/login/aad/callback",
     "https://mlbprops-dev-ui--<new-revision>.victoriousgrass-303f2d5f.eastus2.azurecontainerapps.io/.auth/login/aad/callback",
   ]
   ```
3. Apply:
   ```bash
   terraform apply -target=module.ui
   ```

## Terraform Sensitive Variables

These must be exported as env vars before every `terraform apply` session:

```bash
export TF_VAR_databricks_token=$(grep DATABRICKS_TOKEN c:/Users/Antho/Documents/mlb_props_ui/.env.local | cut -d'=' -f2 | tr -d '"')
export TF_VAR_sql_admin_password="YourPassword"
```

## MSYS Path Conversion (Git Bash on Windows)

When passing Azure resource IDs to Terraform (e.g. `terraform import`), Git Bash mangles
leading `/` into Windows paths. Always prefix with `MSYS_NO_PATHCONV=1`:

```bash
MSYS_NO_PATHCONV=1 terraform import module.ui.azapi_resource.streamlit_auth_config /subscriptions/...
```

## EDGE_THRESHOLD Sync Risk

`app.py` has `EDGE_THRESHOLD = 0.08` which must stay in sync with:
- `notebooks/monte_carlo_simulator.py` → `EDGE_THRESHOLD`
- `notebooks/inference_pipeline.py` → `EDGE_THRESHOLD_OVER/UNDER`

The simulator writes ALL pitcher/line/book combinations to `mart_betting_edges` — not just
flagged ones. The UI applies its own threshold filter. If the threshold changes in the
notebooks, update `app.py` to match or the Place Bets tab will show stale/wrong edges.

## Pipeline Tables the UI Reads

Only 3 tables are coupled to the UI — all training/intermediate models are isolated:

| Table | Used by |
|---|---|
| `main.mlb_props_gold.mart_betting_edges` | Place Bets tab — today's edges |
| `main.mlb_props_gold.bet_results` | All tabs — owned entirely by UI |
| `main.mlb_props_silver.int_pitcher_game_outcomes` | Settle Bets tab — auto-settlement |

## Auto-Settlement Timing

Statcast data for previous night's games is available after `statcast_ingest` runs (~13:00 UTC / 9 AM ET) + `dbt run` completes. Settle Bets tab will show no Statcast data before that window.
