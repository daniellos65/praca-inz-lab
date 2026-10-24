<#
  pomiar-veracrypt.ps1 - pomiar predkosci kryptoanalizy kontenerow VeraCrypt (GPU)

  Dla kazdego kontenera vc-sha512-pim<PIM>.hc uruchamia Hashcat (tryb 13721,
  VeraCrypt SHA-512 + AES) z USTALONA wartoscia PIM odczytana z nazwy pliku,
  mierzy predkosc (Speed.#1) kilka razy i rownolegle loguje stan karty.

  Hashcat czyta kontener bezposrednio - nie trzeba zadnego ekstraktora.
  Atak maska (-a 3) na cyfrach sluzy tylko do zmierzenia predkosci: nie odgaduje
  hasla, tylko pozwala karcie liczyc kandydatow przez zadany czas.

  Uruchomienie (PowerShell, w folderze ze skryptem):
      powershell -ExecutionPolicy Bypass -File .\pomiar-veracrypt.ps1

  Opcje:
      -Hashcat   F:\hashcat                              folder z hashcat.exe
      -Pliki     F:\praca-inz\pliki-testowe              folder z kontenerami vc-*.hc
      -Folder    F:\praca-inz\wyniki\E4\veracrypt        gdzie zapisac wyniki
      -Proby     3                                       liczba prob na kontener
      -Czas      40                                      czas pojedynczej proby [s]

  Wyniki:
      vc-pim<PIM>-<proba>.txt   pelne wyjscie Hashcata
      gpu-log.csv               log karty co 2 s
      podsumowanie.txt          srednia predkosc i liczba iteracji wg PIM
      wyniki-surowe.csv         kazda proba osobno
#>
param(
    [string]$Hashcat = "F:\hashcat",
    [string]$Pliki = "F:\praca-inz\pliki-testowe",
    [string]$Folder = "F:\praca-inz\wyniki\E4\veracrypt",
    [int]$Proby = 3,
    [int]$Czas = 40
)

$ErrorActionPreference = "Continue"
function Info($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Ostrz($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }

$hcExe = Join-Path $Hashcat "hashcat.exe"
if (-not (Test-Path $hcExe)) { Write-Host "Nie znaleziono $hcExe. Podaj -Hashcat <folder>." -ForegroundColor Red; exit 1 }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) { Write-Host "Nie znaleziono nvidia-smi." -ForegroundColor Red; exit 1 }

$kontenery = Get-ChildItem -Path $Pliki -Filter "vc-*.hc" -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -match 'pim(\d+)' } | Sort-Object { [int]([regex]::Match($_.BaseName, 'pim(\d+)').Groups[1].Value) }
if (-not $kontenery) { Write-Host "Brak plikow vc-*pim<liczba>*.hc w $Pliki" -ForegroundColor Red; exit 1 }
Info "Znaleziono kontenery: $($kontenery.Name -join ', ')"

$vm = Get-Process -Name VBoxHeadless, VirtualBoxVM -ErrorAction SilentlyContinue
if ($vm) { Ostrz "Dzialaja maszyny wirtualne - wylacz je przed pomiarem." }

New-Item -ItemType Directory -Force $Folder | Out-Null
Get-ChildItem $Folder -File | Where-Object { $_.Name -match '^(vc-pim.*\.txt|gpu-log\.csv|podsumowanie\.txt|wyniki-surowe\.csv)$' } | Remove-Item -Force
$log = Join-Path $Folder "gpu-log.csv"

# log karty: kazda probka osobnym wywolaniem, dopisywana od razu (odporne na przerwanie)
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
Info "Log karty dziala. Pomiar: $($kontenery.Count) kontenerow x $Proby prob po $Czas s."

$wyniki = @()
$mult = @{ 'H/s' = 1; 'kH/s' = 1e3; 'MH/s' = 1e6; 'GH/s' = 1e9 }
try {
    foreach ($k in $kontenery) {
        $pim = [int]([regex]::Match($k.BaseName, 'pim(\d+)').Groups[1].Value)
        $iter = 15000 + $pim * 1000
        foreach ($i in 1..$Proby) {
            Write-Host ""
            Info "Kontener PIM $pim (iteracje ~$iter), proba $i z $Proby"
            $st = [math]::Max(1, [math]::Floor($Czas / 2))
            Push-Location $Hashcat   # hashcat musi dzialac ze swojego folderu, by znalezc OpenCL/kernels
            $out = & $hcExe -m 13721 "$($k.FullName)" -a 3 "?d?d?d?d?d?d?d?d" `
                --veracrypt-pim-start $pim --veracrypt-pim-stop $pim `
                --runtime $Czas --status --status-timer $st --potfile-disable 2>&1 | ForEach-Object { "$_" }
            Pop-Location
            $out | Set-Content (Join-Path $Folder "vc-pim$pim-$i.txt") -Encoding UTF8
            $speedLine = $out | Where-Object { $_ -match 'Speed\.#' } | Select-Object -First 1
            if ($speedLine -match 'Speed\.#[\d\*]+\.*:\s+([\d\.]+)\s+([kMG]?H/s)') {
                $hs = [double]$matches[1] * $mult[$matches[2]]
                Write-Host ("    {0:N1} H/s" -f $hs)
                $wyniki += [pscustomobject]@{ PIM = $pim; Iteracje = $iter; Proba = $i; HS = $hs }
            } else {
                Ostrz "brak linii Speed - sprawdz plik vc-pim$pim-$i.txt (moze blad odczytu kontenera)"
            }
            Start-Sleep -Seconds 5
        }
    }
}
finally {
    Start-Sleep -Seconds 3
    Stop-Job $logJob -EA SilentlyContinue
    Remove-Job $logJob -Force -EA SilentlyContinue
}

if (-not $wyniki) { Write-Host "Nie zebrano zadnych predkosci. Zajrzyj do plikow vc-pim*.txt." -ForegroundColor Red; exit 1 }

$wyniki | Sort-Object PIM, Proba | Export-Csv (Join-Path $Folder "wyniki-surowe.csv") -NoTypeInformation -Encoding UTF8 -Delimiter ";"

Write-Host ""
Info "Podsumowanie"
$lin = @()
$lin += "{0,-6} {1,-12} {2,14} {3,4} {4,8}" -f "PIM", "Iteracje", "Srednia H/s", "n", "Odch.%"
foreach ($g in ($wyniki | Group-Object PIM | Sort-Object { [int]$_.Name })) {
    $hs = $g.Group.HS; $sr = ($hs | Measure-Object -Average).Average
    $odch = 0
    if ($hs.Count -gt 1) { $odch = [math]::Sqrt((($hs | ForEach-Object { ($_ - $sr) * ($_ - $sr) }) | Measure-Object -Sum).Sum / ($hs.Count - 1)) / $sr * 100 }
    $lin += "{0,-6} {1,-12} {2,14:N1} {3,4} {4,7:N1}%" -f $g.Name, (15000 + [int]$g.Name * 1000), $sr, $g.Count, $odch
}
$lin | ForEach-Object { Write-Host "    $_" }
$lin | Set-Content (Join-Path $Folder "podsumowanie.txt") -Encoding UTF8
Write-Host ""
Write-Host "Gotowe. Wgraj zawartosc $Folder do repozytorium (wyniki/E4/veracrypt)." -ForegroundColor Green
