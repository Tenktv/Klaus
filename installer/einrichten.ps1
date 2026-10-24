# Klaus - Einrichtung nach der Installation (vom Installer aufgerufen, laeuft ohne Admin-Rechte).
#   1. Python 3.11 finden oder installieren (nur fuer diesen Benutzer)
#   2. .venv anlegen, Pakete aus requirements.txt (nur wenn sich die Liste geaendert hat)
#   3. lokale Ersatzstimme (Piper) laden, Browser fuer das Browser-Werkzeug
# -Update: stilles Update - nur was sich geaendert hat, Fenster bleibt nicht offen.
param([Parameter(Mandatory = $true)][string]$Ordner, [switch]$Update)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-Location $Ordner
$Protokoll = Join-Path $Ordner "data\einrichten.log"
New-Item -ItemType Directory -Force -Path (Join-Path $Ordner "data") | Out-Null
Start-Transcript -Path $Protokoll -Append | Out-Null

function Schritt($Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }

function Finde-Python {
    foreach ($kandidat in @(
            { & py -3.11 -c "import sys; print(sys.executable)" 2>$null },
            { & python -c "import sys; assert sys.version_info[:2] == (3, 11); print(sys.executable)" 2>$null })) {
        try { $p = (& $kandidat | Select-Object -Last 1); if ($p -and (Test-Path $p)) { return $p.Trim() } } catch {}
    }
    $lokal = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $lokal) { return $lokal }
    return $null
}

try {
    Schritt "Python 3.11"
    $python = Finde-Python
    if (-not $python) {
        Write-Host "Python 3.11 fehlt - lade den offiziellen Installer von python.org ..."
        $setup = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
        Invoke-WebRequest "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $setup
        Start-Process $setup -Wait -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=1", "Include_test=0"
        $python = Finde-Python
        if (-not $python) { throw "Python 3.11 liess sich nicht installieren." }
    }
    Write-Host "Python: $python"

    $venvPy = Join-Path $Ordner ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Schritt "Eigene Python-Umgebung (.venv)"
        & $python -m venv (Join-Path $Ordner ".venv")
    }

    $req = Join-Path $Ordner "requirements.txt"
    $merker = Join-Path $Ordner "data\requirements.sha256"
    $hash = (Get-FileHash $req -Algorithm SHA256).Hash
    if (-not (Test-Path $merker) -or (Get-Content $merker -Raw).Trim() -ne $hash) {
        Schritt "Pakete installieren (beim ersten Mal 5-15 Minuten, je nach Internet)"
        & $venvPy -m pip install --upgrade pip --quiet
        & $venvPy -m pip install -r $req
        if ($LASTEXITCODE -ne 0) { throw "pip install ist fehlgeschlagen (siehe data\einrichten.log)." }
        & $venvPy -m playwright install chromium
        Set-Content -Path $merker -Value $hash
    }
    else { Write-Host "Pakete sind aktuell." }

    $piper = Join-Path $Ordner "data\stimmen\de_DE-thorsten-high.onnx"
    if (-not (Test-Path $piper)) {
        Schritt "Lokale Ersatzstimme (offline)"
        & $venvPy -m piper.download_voices --download-dir (Join-Path $Ordner "data\stimmen") de_DE-thorsten-high
    }

    Schritt "Fertig"
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host "Tipp: Fuer Antworten ganz ohne Internet zusaetzlich Ollama installieren (ollama.com)." -ForegroundColor Yellow
    }
    Stop-Transcript | Out-Null
    if (-not $Update) { Start-Sleep -Seconds 3 }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "FEHLER: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Protokoll: $Protokoll"
    Stop-Transcript | Out-Null
    if (-not $Update) { Read-Host "Enter zum Schliessen" }
    exit 1
}
