<#
  pomiar-argon2.ps1 - skalowanie pamieci Argon2: predkosc GPU i CPU (hashcat -m 34000)

  Dla kazdego hasha argon2-m*.hash (pamiec 64/256/1024 MiB) mierzy predkosc na GPU
  i na CPU, po czym liczy stosunek GPU/CPU. Oczekiwanie: wraz ze wzrostem pamieci
  stosunek GPU/CPU maleje (karta nie miesci wielu rownoleglych instancji w VRAM).

  Hashe generuje wczesniej tools/gen-argon2.py. CPU liczony przez OpenCL
  (--backend-ignore-cuda -D 1), GPU przez CUDA (-d GpuDev).

  Uruchomienie:
      powershell -ExecutionPolicy Bypass -File .\pomiar-argon2.ps1

  Opcje:
      -Hashcat F:\hashcat
      -Pliki   F:\praca-inz\e4b                 folder z argon2-m*.hash
      -Folder  F:\praca-inz\wyniki\E4\argon2-skalowanie
      -GpuDev  1
      -Proby   2
      -Czas    40
#>
param(
    [string]$Hashcat = "F:\hashcat",
    [string]$Pliki = "F:\praca-inz\e4b",
    [string]$Folder = "F:\praca-inz\wyniki\E4\argon2-skalowanie",
    [int]$GpuDev = 1,
    [int]$Proby = 2,
    [int]$Czas = 40
)

$ErrorActionPreference = "Continue"
function Info($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Ostrz($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }

$hcExe = Join-Path $Hashcat "hashcat.exe"
if (-not (Test-Path $hcExe)) { Write-Host "Nie znaleziono $hcExe." -ForegroundColor Red; exit 1 }
$hashe = Get-ChildItem -Path $Pliki -Filter "argon2-m*.hash" -EA SilentlyContinue | Sort-Object { [int]([regex]::Match($_.BaseName, 'm(\d+)').Groups[1].Value) }
if (-not $hashe) { Write-Host "Brak plikow argon2-m*.hash w $Pliki. Najpierw uruchom gen-argon2.py." -ForegroundColor Red; exit 1 }
Info "Hashe: $($hashe.Name -join ', ')"

New-Item -ItemType Directory -Force $Folder | Out-Null
Get-ChildItem $Folder -File -EA SilentlyContinue | Where-Object { $_.Name -match '\.(txt|csv)$' } | Remove-Item -Force
$mult = @{ 'H/s' = 1; 'kH/s' = 1e3; 'MH/s' = 1e6; 'GH/s' = 1e9 }

function Zmierz($hashPath, $kind) {
    Push-Location $Hashcat
    if ($kind -eq "cpu") {
        $out = & $hcExe -m 34000 "$hashPath" -a 3 "?d?d?d?d?d?d?d?d" --backend-ignore-cuda -D 1 --runtime $Czas --status --status-timer ([math]::Max(10, [math]::Floor($Czas / 2))) --potfile-disable 2>&1 | ForEach-Object { "$_" }
    } else {
        $out = & $hcExe -m 34000 "$hashPath" -a 3 "?d?d?d?d?d?d?d?d" -d $GpuDev --runtime $Czas --status --status-timer ([math]::Max(10, [math]::Floor($Czas / 2))) --potfile-disable 2>&1 | ForEach-Object { "$_" }
    }
    Pop-Location
    $sl = $out | Where-Object { $_ -match 'Speed\.#' } | Select-Object -First 1
    $hs = $null
    if ($sl -match 'Speed\.#[\d\*]+\.*:\s+([\d\.]+)\s+([kMG]?H/s)') { $hs = [double]$matches[1] * $mult[$matches[2]] }
    return @{ Out = ($out -join "`n"); HS = $hs }
}

$wyniki = @()
foreach ($h in $hashe) {
    $mib = [int]([regex]::Match($h.BaseName, 'm(\d+)').Groups[1].Value)
    foreach ($kind in @("gpu", "cpu")) {
        for ($i = 1; $i -le $Proby; $i++) {
            Write-Host ""
            Info "Argon2 $mib MiB na $($kind.ToUpper()) - proba $i z $Proby"
            $r = Zmierz $h.FullName $kind
            $r.Out | Set-Content (Join-Path $Folder "argon2-$mib-$kind-$i.txt") -Encoding UTF8
            if ($null -ne $r.HS) {
                Write-Host ("    {0:N1} H/s" -f $r.HS)
                $wyniki += [pscustomobject]@{ MiB = $mib; Urzadzenie = $kind; Proba = $i; HS = $r.HS }
            } else { Ostrz "brak Speed - sprawdz argon2-$mib-$kind-$i.txt (mozliwy brak pamieci GPU)" }
        }
    }
}

if (-not $wyniki) { Write-Host "Nie zebrano wynikow." -ForegroundColor Red; exit 1 }
$wyniki | Export-Csv (Join-Path $Folder "wyniki-surowe.csv") -NoTypeInformation -Encoding UTF8 -Delimiter ";"

Write-Host ""; Info "Podsumowanie - skalowanie pamieci Argon2"
$lin = @()
$lin += "{0,-10} {1,16} {2,16} {3,12}" -f "Pamiec", "GPU [H/s]", "CPU [H/s]", "GPU/CPU"
foreach ($g in ($wyniki | Group-Object MiB | Sort-Object { [int]$_.Name })) {
    $gs = ($g.Group | Where-Object Urzadzenie -eq "gpu" | Measure-Object HS -Average).Average
    $cs = ($g.Group | Where-Object Urzadzenie -eq "cpu" | Measure-Object HS -Average).Average
    $ratio = if ($cs -gt 0) { "{0:N1}x" -f ($gs / $cs) } else { "-" }
    $lin += "{0,-10} {1,16:N1} {2,16:N1} {3,12}" -f "$($g.Name) MiB", $gs, $cs, $ratio
}
$lin | ForEach-Object { Write-Host "    $_" }
$lin | Set-Content (Join-Path $Folder "podsumowanie.txt") -Encoding UTF8
Write-Host ""
Write-Host "Gotowe. Wgraj zawartosc $Folder do repozytorium (wyniki/E4/argon2-skalowanie)." -ForegroundColor Green
