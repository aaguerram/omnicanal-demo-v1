# One-time creation of the GCP service account the Lambda uses to
# authenticate to Firestore (RAG reads) -- the only Google service this
# project still uses; chat and embeddings run on Amazon Bedrock instead (see
# core/settings.py, features/*/graph.py). The resulting JSON key gets stored
# in AWS Secrets Manager by scripts/provision.ps1 -- it's never committed to
# the repo.
#
# Prereq: `gcloud auth login` + `gcloud config set project skincare-ai-commerce`
# with an account that can create service accounts / grant IAM roles on that
# project.
#
# Run from the project root: .\scripts\create_gcp_service_account.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Project = "skincare-ai-commerce"
$SaName = "agentic-skincare-lambda"
$SaEmail = "$SaName@$Project.iam.gserviceaccount.com"
$KeyFile = "$root\gcp-service-account-key.json"   # .gitignore'd -- see .gitignore

if (Test-Path $KeyFile) {
    throw "$KeyFile already exists -- delete it first if you really want a new key (old key keeps working until explicitly revoked)."
}

gcloud iam service-accounts create $SaName `
    --project $Project `
    --display-name "agentic-skincare-backend Lambda"

# roles/datastore.viewer: solo lectura -- el Lambda unicamente consulta el
# catalogo (FirestoreVectorStore.similarity_search en info_productos/graph.py),
# nunca escribe. La ingesta de PDFs (scripts/ingestar_pdfs.py) sigue corriendo
# con las credenciales ADC del desarrollador, no con esta service account.
gcloud projects add-iam-policy-binding $Project `
    --member "serviceAccount:$SaEmail" `
    --role "roles/datastore.viewer" `
    --condition None

gcloud iam service-accounts keys create $KeyFile `
    --iam-account $SaEmail

Write-Host "`nCreated $SaEmail and wrote key to $KeyFile."
Write-Host "Next: `$env:GCP_SERVICE_ACCOUNT_KEY_FILE = '$KeyFile'; .\scripts\provision.ps1"
