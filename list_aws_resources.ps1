# Comprobar si AWS CLI está instalado en el sistema
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: AWS CLI no está instalado o no se encuentra en el PATH de Windows." -ForegroundColor Red
    Write-Host "Puedes instalarlo ejecutando en una consola de Administrador:" -ForegroundColor Yellow
    Write-Host "winget install Amazon.AWSCLI" -ForegroundColor Cyan
    Write-Host "O descargando el instalador oficial desde: https://awscli.amazonaws.com/AWSCLIV2.msi" -ForegroundColor Cyan
    Write-Host "Recuerda reiniciar tu terminal o VS Code después de instalarlo." -ForegroundColor Yellow
    exit 1
}
# Comprobar si la sesión está autenticada/configurada
Write-Host "Verificando conexión con AWS..." -ForegroundColor Green
$identity = aws sts get-caller-identity --query "Arn" --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: No se pudo conectar a AWS. Asegúrate de haber ejecutado 'aws configure' primero." -ForegroundColor Red
    exit 1
}
Write-Host "Autenticado como: $identity" -ForegroundColor Cyan
# Obtener todas las regiones disponibles
Write-Host "`nObteniendo regiones activas de AWS..." -ForegroundColor Green
try {
    $regionsJson = aws ec2 describe-regions --query "Regions[].RegionName" --output json
    $regions = $regionsJson | ConvertFrom-Json
} catch {
    Write-Host "ERROR al obtener las regiones: $_" -ForegroundColor Red
    exit 1
}
Write-Host "Se encontraron $($regions.Count) regiones. Iniciando búsqueda de recursos..." -ForegroundColor Green
foreach ($region in $regions) {
    Write-Host "`n===============================================" -ForegroundColor Yellow
    Write-Host " Región: $region" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Yellow
    
    # Consultar los recursos usando la API de Tagging (soporta la gran mayoría de recursos regionales)
    Write-Host "Buscando componentes..." -ForegroundColor Gray
    $resources = aws resourcegroupstaggingapi get-resources --region $region --query "ResourceTagMappingList[].ResourceARN" --output json | ConvertFrom-Json
    
    if ($resources -and $resources.Count -gt 0) {
        Write-Host "Se encontraron $($resources.Count) componentes en $region`:" -ForegroundColor Green
        foreach ($arn in $resources) {
            Write-Host " - $arn" -ForegroundColor White
        }
    } else {
        Write-Host "No se encontraron componentes en esta región." -ForegroundColor DarkGray
    }
}
Write-Host "`nBúsqueda finalizada." -ForegroundColor Green
