# Einmal als Administrator ausfuehren (Rechtsklick -> "Mit PowerShell ausfuehren" bzw. Admin-PowerShell):
# Verhindert, dass Maus, Tastatur oder Netzwerkkarte den PC im Energiesparmodus ungewollt wecken.
# Geweckt wird danach NUR noch vom Zeitplan (Aufgabe "Klaus-Aufwecken") und vom Einschaltknopf.
# Rueckgaengig: Skript mit -Rueckgaengig starten.
param([switch]$Rueckgaengig)
$geraete = powercfg /devicequery wake_armed | Where-Object { $_ -and $_ -notmatch "^NONE$" }
if ($Rueckgaengig) {
    Get-Content "$PSScriptRoot\schlafmodus_zuvor.txt" -ErrorAction SilentlyContinue | ForEach-Object { powercfg /deviceenablewake "$_" }
    Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName "Wake on pattern match" -DisplayValue "Enabled" -ErrorAction SilentlyContinue }
    "Zurueckgesetzt."; return
}
$geraete | Set-Content "$PSScriptRoot\schlafmodus_zuvor.txt" -Encoding utf8     # Merkliste fuer -Rueckgaengig
foreach ($g in $geraete) { powercfg /devicedisablewake "$g"; "Weckrecht entzogen: $g" }
Get-NetAdapter -Physical | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName "Wake on pattern match" -DisplayValue "Disabled" -ErrorAction SilentlyContinue; "Netzwerkkarte $($_.Name): Wake on pattern match aus" }
"Fertig. Jetzt weckt nur noch der Zeitplan (und der Einschaltknopf). Pruefen: powercfg /devicequery wake_armed"
