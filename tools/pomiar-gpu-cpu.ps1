<#
  pomiar-gpu-cpu.ps1 - porownanie predkosci GPU i CPU dla kilku algorytmow

  Dla kazdego trybu uruchamia wbudowany test wydajnosci Hashcata (-b) osobno
  na GPU i na CPU (wybor urzadzenia przez -d), po czym liczy stosunek GPU/CPU.
  Kluczowa metryka rozdzialu 5: dla funkcji memory-hard (Argon2) przewaga GPU
  nad CPU powinna byc wyraznie mniejsza niz dla funkcji szybkich (MD5).

  WYMAGA: zainstalowanego Intel CPU Runtime for OpenCL (CPU widoczne w `hashcat -I`).

  Uruchomienie (PowerShell, w folderze ze skryptem):
      powershell -ExecutionPolicy Bypass -File .\pomiar-gpu-cpu.ps1

  Opcje:
      -Hashcat F:\hashcat
      -Folder  F:\praca-inz\wyniki\E4\gpu-cpu
      -Tryby   "0,11600,13400,13721,34300"   tryby Hashcata
      -GpuDev  1      numer urzadzenia GPU (z `hashcat -I`)
      -Proby   2      liczba prob na (tryb, urzadzenie)

  Wyniki:
      <tryb>-<gpu|cpu>-<proba>.txt   pelne wyjscie Hashcata
      wyniki-surowe.csv              kazdy pomiar osobno
      podsumowanie.txt               GPU, CPU i stosunek GPU/CPU wg trybu
#>
param(
    [string]$Hashcat = "F:\hashcat",
    [string]$Folder = "F:\praca-inz\wyniki\E4\gpu-cpu",
    [string]$Tryby = "0,11600,13400,13721,34300",
    [int]$GpuDev = 1,
    [int]$Proby = 2
)

$ErrorActionPreference = "Continue"
function Info($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Ostrz($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }

$hcExe = Join-Path $Hashcat "hashcat.exe"
if (-not (Test-Path $hcExe)) { Write-Host "Nie znaleziono $hcExe." -ForegroundColor Red; exit 1 }
$ListaTrybow = @($Tryby -split '[,; ]+' | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
if (-not $ListaTrybow) { Write-Host "Zla lista trybow: $Tryby" -ForegroundColor Red; exit 1 }

$Nazwy = @{ "0" = "MD5"; "1000" = "NTLM"; "11600" = "7-Zip"; "13400" = "KeePass AES-KDF"; "13721" = "VeraCrypt"; "34300" = "KeePass Argon2" }
$mult = @{ 'H/s' = 1; 'kH/s' = 1e3; 'MH/s' = 1e6; 'GH/s' = 1e9 }

New-Item -ItemType Directory -Force $Folder | Out-Null
Get-ChildItem $Folder -File -EA SilentlyContinue | Where-Object { $_.Name -match '\.(txt|csv)$' } | Remove-Item -Force
Info "Porownanie GPU (dev $GpuDev, CUDA) vs CPU (OpenCL). Tryby: $($ListaTrybow -join ', '). UWAGA: CPU liczy wolniej, calosc moze potrwac."

function Zmierz($mode, $kind) {
    Push-Location $Hashcat
    if ($kind -eq "cpu") {
        # CPU przez OpenCL: wylacz CUDA i wybierz urzadzenia typu CPU (-D 1)
        $out = & $hcExe -b -m $mode --backend-ignore-cuda -D 1 2>&1 | ForEach-Object { "$_" }
    } else {
        $out = & $hcExe -b -m $mode -d $GpuDev 2>&1 | ForEach-Object { "$_" }
    }
    Pop-Location
    $sl = $out | Where-Object { $_ -match 'Speed\.#' } | Select-Object -First 1
    $hs = $null
    if ($sl -match 'Speed\.#[\d\*]+\.*:\s+([\d\.]+)\s+([kMG]?H/s)') { $hs = [double]$matches[1] * $mult[$matches[2]] }
    return @{ Out = ($out -join "`n"); HS = $hs }
}

$wyniki = @()
foreach ($m in $ListaTrybow) {
    $nazwa = $Nazwy["$m"]; if (-not $nazwa) { $nazwa = "tryb$m" }
    foreach ($kind in @("gpu", "cpu")) {
        for ($i = 1; $i -le $Proby; $i++) {
            Write-Host ""
            Info "$nazwa ($m) na $($kind.ToUpper()) - proba $i z $Proby"
            $r = Zmierz $m $kind
            $r.Out | Set-Content (Join-Path $Folder "$m-$kind-$i.txt") -Encoding UTF8
            if ($null -ne $r.HS) {
                Write-Host ("    {0:N1} H/s" -f $r.HS)
                $wyniki += [pscustomobject]@{ Tryb = $m; Algorytm = $nazwa; Urzadzenie = $kind; Proba = $i; HS = $r.HS }
            } else { Ostrz "brak Speed - sprawdz $m-$kind-$i.txt" }
        }
    }
}

if (-not $wyniki) { Write-Host "Nie zebrano wynikow." -ForegroundColor Red; exit 1 }
$wyniki | Export-Csv (Join-Path $Folder "wyniki-surowe.csv") -NoTypeInformation -Encoding UTF8 -Delimiter ";"

Write-Host ""; Info "Podsumowanie (srednia z prob)"
$lin = @()
$lin += "{0,-8} {1,-16} {2,18} {3,18} {4,12}" -f "Tryb", "Algorytm", "GPU [H/s]", "CPU [H/s]", "GPU/CPU"
foreach ($m in $ListaTrybow) {
    $g = $wyniki | Where-Object { $_.Tryb -eq $m -and $_.Urzadzenie -eq "gpu" }
    $c = $wyniki | Where-Object { $_.Tryb -eq $m -and $_.Urzadzenie -eq "cpu" }
    if (-not $g -or -not $c) { continue }
    $gs = ($g.HS | Measure-Object -Average).Average
    $cs = ($c.HS | Measure-Object -Average).Average
    $ratio = if ($cs -gt 0) { $gs / $cs } else { 0 }
    $nazwa = $Nazwy["$m"]; if (-not $nazwa) { $nazwa = "tryb$m" }
    $lin += "{0,-8} {1,-16} {2,18:N1} {3,18:N1} {4,10:N1}x" -f $m, $nazwa, $gs, $cs, $ratio
}
$lin | ForEach-Object { Write-Host "    $_" }
$lin | Set-Content (Join-Path $Folder "podsumowanie.txt") -Encoding UTF8
Write-Host ""
Write-Host "Gotowe. Wgraj zawartosc $Folder do repozytorium (wyniki/E4/gpu-cpu)." -ForegroundColor Green
