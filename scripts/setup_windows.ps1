# Windows setup + check for enterprise-copilot.
# Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
# Everything shown on screen is also saved to setup-log.txt (safe to share: no secrets are printed).

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Start-Transcript -Path (Join-Path $root 'setup-log.txt') -Force | Out-Null
$script:results = @()

function Run([string]$exe, [string[]]$argv) {
    $global:LASTEXITCODE = 0
    & $exe @argv 2>&1 | ForEach-Object { Write-Host "    $_" }
}

function Step([string]$name, [scriptblock]$block) {
    Write-Host ""
    Write-Host "=== $name ===" -ForegroundColor Cyan
    try {
        $global:LASTEXITCODE = 0
        & $block
        if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
        Write-Host "[OK] $name" -ForegroundColor Green
        $script:results += "[OK]   $name"
        return $true
    } catch {
        Write-Host "[FAIL] $name -> $_" -ForegroundColor Red
        $script:results += "[FAIL] $name -> $_"
        return $false
    }
}

Write-Host "Windows: $([Environment]::OSVersion.VersionString)  PowerShell: $($PSVersionTable.PSVersion)"

$pyOk = Step 'Python 3.11+' {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw 'python not found - install Python 3.11+ from python.org and tick "Add to PATH"' }
    Write-Host "    path: $($cmd.Source)"
    Run 'python' @('--version')
    $ok = (& python -c "import sys; print(sys.version_info >= (3, 11))") 2>$null
    if ("$ok".Trim() -ne 'True') { throw 'Python is older than 3.11 (or is the Microsoft Store stub)' }
}

$dockerOk = Step 'Docker Desktop running' {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'docker not found - install Docker Desktop' }
    Run 'docker' @('version', '--format', 'client {{.Client.Version}} / server {{.Server.Version}}')
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine not running - open Docker Desktop and wait until it says "Engine running"' }
}

if ($pyOk) {
    $venvOk = Step 'Virtual env (.venv)' {
        if (-not (Test-Path '.venv\Scripts\python.exe')) { Run 'python' @('-m', 'venv', '.venv') }
        if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'could not create .venv' }
    }
    $py = Join-Path $root '.venv\Scripts\python.exe'
    if ($venvOk) {
        $pipOk = Step 'pip install -r requirements.txt' {
            Run $py @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', '-r', 'requirements.txt')
        }
    }
    Step '.env file' {
        if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env'; Write-Host '    created .env from .env.example' }
        else { Write-Host '    .env already exists (not changed)' }
    } | Out-Null
}

if ($dockerOk) {
    $dbOk = Step 'docker compose up -d (Postgres + pgvector)' {
        Run 'docker' @('compose', 'up', '-d')
        if ($LASTEXITCODE -ne 0) { throw "docker compose failed (exit $LASTEXITCODE)" }
        $status = ''
        for ($i = 0; $i -lt 30; $i++) {
            $status = (& docker inspect -f '{{.State.Health.Status}}' copilot-db) 2>$null
            if ("$status".Trim() -eq 'healthy') { break }
            Start-Sleep -Seconds 2
        }
        Write-Host "    copilot-db health: $status"
        if ("$status".Trim() -ne 'healthy') { throw 'database did not become healthy in 60s' }
    }
}

if ($pyOk -and $pipOk -and $dbOk) {
    Step 'Load seed data' { Run $py @('scripts\load_seed.py') } | Out-Null
    Step 'pytest' { Run $py @('-m', 'pytest', '-q', '-p', 'no:cacheprovider') } | Out-Null
}
if ($pyOk -and $pipOk) {
    Write-Host ""
    Write-Host "=== check_setup.py (LLM lines fail until Azure keys are in .env - expected) ===" -ForegroundColor Cyan
    Run $py @('scripts\check_setup.py')
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
$script:results | ForEach-Object { Write-Host $_ }
Stop-Transcript | Out-Null
Write-Host ""
Write-Host "Log saved to setup-log.txt"
