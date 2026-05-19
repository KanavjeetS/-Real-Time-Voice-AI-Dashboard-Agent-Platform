# Deploy AI Calling Agent API to Railway (run from repo root after: railway login)
# Non-interactive: $env:RAILWAY_TOKEN = "..."  from https://railway.com/account/tokens
if ($env:RAILWAY_TOKEN) { $env:RAILWAY_API_TOKEN = $env:RAILWAY_TOKEN }

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Railway = "npx"
$RailwayArgs = @("@railway/cli")

function Invoke-Railway {
    param([string[]]$CmdArgs)
    & $Railway @RailwayArgs @CmdArgs
    if ($LASTEXITCODE -ne 0) { throw "railway $($CmdArgs -join ' ') failed ($LASTEXITCODE)" }
}

Write-Host "Checking Railway auth..." -ForegroundColor Cyan
& $Railway @RailwayArgs whoami 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Run: npx @railway/cli login" -ForegroundColor Yellow
    exit 1
}

$projectName = "ai-calling-agent-api"
$statusJson = & $Railway @RailwayArgs status --json 2>$null
$linked = $LASTEXITCODE -eq 0 -and $statusJson -match '"project"'
if (-not $linked) {
    Write-Host "Creating Railway project: $projectName" -ForegroundColor Cyan
    Invoke-Railway @("init", "-n", $projectName, "--json")
    Invoke-Railway @("service", "link", $projectName)
}

Write-Host "Loading .env..." -ForegroundColor Cyan
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) { throw "Missing .env at $envFile" }

$vars = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    $vars[$k.Trim()] = $v.Trim()
}

$production = @{
    APP_ENV                    = "production"
    LOG_LEVEL                  = "INFO"
    CORS_ORIGINS               = "https://frontend-omega-six-37.vercel.app"
    STARTUP_WARM_MODELS        = "true"
    USE_DATABASE               = "true"
    MODEL_TIER                 = "free"
    DEFAULT_PHONE_REGION       = "IN"
    MAX_CONCURRENT_CALLS       = "10"
    CALL_TIMEOUT_SECONDS       = "300"
    GROQ_API_KEY               = $vars["GROQ_API_KEY"]
    GROQ_LLM_MODEL             = $vars["GROQ_LLM_MODEL"]
    GROQ_STT_MODEL              = $vars["GROQ_STT_MODEL"]
    GROQ_STT_LANGUAGE           = $vars["GROQ_STT_LANGUAGE"]
    TWILIO_ACCOUNT_SID         = $vars["TWILIO_ACCOUNT_SID"]
    TWILIO_AUTH_TOKEN          = $vars["TWILIO_AUTH_TOKEN"]
    TWILIO_PHONE_NUMBER        = $vars["TWILIO_PHONE_NUMBER"]
    DATABASE_URL               = $vars["DATABASE_URL"]
    REDIS_URL                  = $vars["REDIS_URL"]
    SUPABASE_URL               = $vars["SUPABASE_URL"]
    SUPABASE_ANON_KEY          = $vars["SUPABASE_ANON_KEY"]
}

Write-Host "Deploying Docker service (creates service if needed)..." -ForegroundColor Cyan
Invoke-Railway @("up", "--detach")

foreach ($kv in $production.GetEnumerator()) {
    if ([string]::IsNullOrWhiteSpace($kv.Value)) { continue }
    Write-Host "  set $($kv.Key)" -ForegroundColor DarkGray
    $pair = "$($kv.Key)=$($kv.Value)"
    Invoke-Railway @("variable", "set", $pair, "--skip-deploys")
}

Write-Host "Generating public domain..." -ForegroundColor Cyan
$domainOut = & $Railway @RailwayArgs domain 2>&1 | Out-String
Write-Host $domainOut

$domain = ($domainOut | Select-String -Pattern 'https://[\w.-]+\.up\.railway\.app' -AllMatches).Matches | Select-Object -Last 1
if (-not $domain) {
    $domain = (& $Railway @RailwayArgs status --json 2>$null | ConvertFrom-Json).url
}
if ($domain) {
    $base = $domain.Value.TrimEnd('/')
    if ($base -notmatch '^https://') { $base = "https://$base" }
    Write-Host "Setting TWILIO_WEBHOOK_BASE_URL=$base" -ForegroundColor Green
    Invoke-Railway @("variable", "set", "TWILIO_WEBHOOK_BASE_URL=$base")
    Invoke-Railway @("up", "--detach")
    Write-Host ""
    Write-Host "DONE. API URL: $base" -ForegroundColor Green
    Write-Host "Health:     $base/health"
    Write-Host ""
    Write-Host "Update Vercel: NEXT_PUBLIC_API_URL=$base"
    Write-Host "  cd frontend && npx vercel env add NEXT_PUBLIC_API_URL production"
} else {
    Write-Host "Could not detect domain. Set TWILIO_WEBHOOK_BASE_URL manually in Railway dashboard." -ForegroundColor Yellow
}
