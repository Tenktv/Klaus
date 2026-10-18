param([switch]$Administrator)
$ErrorActionPreference = 'Stop'
$gamePython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$gameScript = Join-Path $PSScriptRoot 'src\genshin_agent\app.py'
if (!(Test-Path -LiteralPath $gamePython)) { throw 'Die Klaus-Python-Umgebung fehlt.' }
$gameArguments = '"' + $gameScript + '"'
if ($Administrator) {
    # Windows zeigt UAC. Der Benutzer bestaetigt selbst; Klaus bleibt normal.
    Start-Process -FilePath $gamePython -ArgumentList $gameArguments -WorkingDirectory $PSScriptRoot -Verb RunAs -WindowStyle Hidden
} else {
    Start-Process -FilePath $gamePython -ArgumentList $gameArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
