<#
  pomiar-hash.ps1 - pomiar predkosci Hashcata dla pojedynczego pliku z hashem (GPU)

  Mierzy predkosc (Speed.#1) dla podanego hasha i trybu, kilka razy, z logiem karty.
  Atak maska (-a 3) na cyfrach sluzy tylko do zmierzenia predkosci; nie odgaduje hasla.

  Uruchomienie (PowerShell):
    powershell -ExecutionPolicy Bypass -File .\pomiar-hash.ps1 -HashFile F:\praca-inz\e4b\test-7zip.hash -Mode 11600 -Nazwa 7zip
    powershell -ExecutionPolicy Bypass -File .\pomiar-hash.ps1 -HashFile F:\praca-inz\e4b\kp-aeskdf-kdbx31.hash -Mode 13400 -Nazwa keepass-aeskdf

  Opcje:
    -HashFile <plik>   plik z hashem (wymagany)
    -Mode <nr>         tryb Hashcata (wymagany): 11600 = 7-Zip, 13400 = KeePass KDBX1/2 (AES-KDF)
    -Nazwa <etykieta>  nazwa uzyta w plikach wynikowych (wymagana)
    -Hashcat F:\hashcat
    -Folder  F:\praca-inz\wyniki\E4\pozostale
    -Proby 3
    -Czas 40
#>
param(
    [Parameter(Mandatory = $true)][string]$HashFile,
    [Parameter(Mandatory = $true)][int]$Mode,
    [Parameter(Mandatory = $true)][string]$Nazwa,
    [string]$Hashcat = "F:\hashcat",
    [string]$Folder = "F:\praca-inz\wyniki\E4\pozostale",
    [int]$Proby = 3,
    [int]$Czas = 40
)

$ErrorActionPreference = "Continue"
function Info($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Ostrz($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }

$hcExe = Join-Path $Hashcat "hashcat.exe"
if (-not (Test-Path $hcExe)) { Write-Host "Nie znaleziono $hcExe. Podaj -Hashcat <folder>." -ForegroundColor Red; exit 1 }
if (-not (Test-Path $HashFile)) { Write-Host "Nie znaleziono pliku z hashem: $HashFile" -ForegroundColor Red; exit 1 }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) { Write-Host "Nie znaleziono nvidia-smi." -ForegroundColor Red; exit 1 }
$HashFile = (Resolve-Path $HashFile).Path

$vm = Get-Process -Name VBoxHeadless, VirtualBoxVM -ErrorAction SilentlyContinue
if ($vm) { Ostrz "Dzialaja maszyny wirtualne - wylacz je przed pomiarem." }

New-Item -ItemType Directory -Force $Folder | Out-Null
$safe = $Nazwa -replace '[^\w\-]', '_'
Get-ChildItem $Folder -File | Where-Object { $_.Name -match "^$([regex]::Escape($safe))-(\d+\.txt)$" -or $_.Name -eq "gpu-log-$safe.csv" } | Remove-Item -Force
# Oczysc plik z hashem: usun BOM i puste linie (czesta przyczyna "Token length exception"),
# zapisz czysta kopie w folderze wynikow i to jej uzyj do pomiaru (oryginal bez zmian).
$HashClean = Join-Path $Folder "$safe.hash"
$linieHash = Get-Content $HashFile | Where-Object { $_.Trim() -ne "" }
if (-not $linieHash) { Write-Host "Plik z hashem jest pusty: $HashFile" -ForegroundColor Red; exit 1 }
[IO.File]::WriteAllText($HashClean, ($linieHash -join "`n") + "`n")
Info "Oczyszczony hash: $HashClean (linii: $($linieHash.Count))"

$log = Join-Path $Folder "gpu-log-$safe.csv"

$logJob = Start-Job -ArgumentList $smi.Source, $log -ScriptBlock {
    param($smiExe, $plik)
    "timestamp, temperature.gpu, clocks.sm [MHz], clocks.mem [MHz], power.draw [W], utilization.gpu [%]" | Set-Content $plik -Encoding UTF8
    while ($true) {
        & $smiExe --query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.mem,power.draw,utilization.gpu --format=csv,noheader | Add-Content $plik -Encoding UTF8
        Start-Sleep -Seconds 2
    }
}
Start-Sleep -Seconds 7
if (-not (Test-Path $log) -or @(Get-Content $log).Count -lt 2) {
    Stop-Job $logJob -EA SilentlyContinue; Remove-Job $logJob -Force -EA SilentlyContinue
    Write-Host "Log nvidia-smi nie zbiera danych - przerwano." -ForegroundColor Red; exit 1
}
Info "Pomiar: $Nazwa (tryb $Mode), $Proby prob po $Czas s. Log karty: $log"

$hs = @()
$mult = @{ 'H/s' = 1; 'kH/s' = 1e3; 'MH/s' = 1e6; 'GH/s' = 1e9 }
try {
    foreach ($i in 1..$Proby) {
        Write-Host ""
        Info "$Nazwa - proba $i z $Proby"
        $st = [math]::Max(1, [math]::Floor($Czas / 2))
        Push-Location $Hashcat
        $out = & $hcExe -m $Mode "$HashClean" -a 3 "?d?d?d?d?d?d?d?d" `
            --runtime $Czas --status --status-timer $st --potfile-disable 2>&1 | ForEach-Object { "$_" }
        Pop-Location
        $out | Set-Content (Join-Path $Folder "$safe-$i.txt") -Encoding UTF8
        $sl = $out | Where-Object { $_ -match 'Speed\.#' } | Select-Object -First 1
        if ($sl -match 'Speed\.#[\d\*]+\.*:\s+([\d\.]+)\s+([kMG]?H/s)') {
            $v = [double]$matches[1] * $mult[$matches[2]]
            Write-Host ("    {0:N1} H/s" -f $v); $hs += $v
        } else { Ostrz "brak linii Speed - sprawdz plik $safe-$i.txt" }
        Start-Sleep -Seconds 5
    }
}
finally {
    Start-Sleep -Seconds 3
    Stop-Job $logJob -EA SilentlyContinue
    Remove-Job $logJob -Force -EA SilentlyContinue
}

if (-not $hs) { Write-Host "Nie zebrano predkosci. Zajrzyj do plikow $safe-*.txt." -ForegroundColor Red; exit 1 }
$sr = ($hs | Measure-Object -Average).Average
$odch = 0
if ($hs.Count -gt 1) { $odch = [math]::Sqrt((($hs | ForEach-Object { ($_ - $sr) * ($_ - $sr) }) | Measure-Object -Sum).Sum / ($hs.Count - 1)) / $sr * 100 }
$pod = "{0} (tryb {1}): srednia {2:N1} H/s, n={3}, odch. {4:N1}%" -f $Nazwa, $Mode, $sr, $hs.Count, $odch
Write-Host ""; Write-Host "    $pod" -ForegroundColor Green
$pod | Add-Content (Join-Path $Folder "podsumowanie.txt") -Encoding UTF8
Write-Host "Dopisano do $Folder\podsumowanie.txt. Wgraj folder 'pozostale' do repo (wyniki/E4/pozostale)."
