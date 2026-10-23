<#
  pomiar-bench.ps1 - test wydajnosci Hashcata (tryb -b) z logiem temperatury GPU

  Dla kazdego trybu wykonuje kilka prob, rownolegle zapisuje co 2 s temperature,
  taktowanie, pobor mocy i obciazenie karty (nvidia-smi), a na koncu podsumowuje
  wyniki pomiarow i logu.

  Uruchomienie (PowerShell, w folderze ze skryptem):
      powershell -ExecutionPolicy Bypass -File .\pomiar-bench.ps1

  Opcje:
      -Hashcat F:\hashcat                        folder z hashcat.exe
      -Folder  F:\praca-inz\wyniki\E4\pomiar1-powtorka   gdzie zapisac wyniki
      -Tryby   0,1000,11600,13721,13400,34300    tryby Hashcata
      -Proby   3                                 liczba prob na tryb

  Wyniki (w folderze -Folder):
      bench-m<tryb>-<proba>.txt   pelne wyjscie Hashcata (UTF-8)
      przebiegi.csv               poczatek i koniec kazdej proby
      gpu-log.csv                 log karty co 2 s
      log-podsumowanie.txt        temperatura, taktowanie, moc podczas obciazenia
      podsumowanie.txt, wyniki-surowe.csv   (jesli obok jest podsumuj-pomiary.ps1)
#>
param(
    [string]$Hashcat = "F:\hashcat",
    [string]$Folder = "F:\praca-inz\wyniki\E4\pomiar1-powtorka",
    [string]$Tryby = "0,1000,11600,13721,13400,34300",
    [int]$Proby = 3
)

$ErrorActionPreference = "Continue"
$Tryby = @($Tryby -split '[,; ]+' | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
function Info($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Ostrz($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }

# --- sprawdzenia -------------------------------------------------------------
$hcExe = Join-Path $Hashcat "hashcat.exe"
if (-not (Test-Path $hcExe)) { Write-Host "Nie znaleziono $hcExe. Podaj folder: -Hashcat C:\sciezka" -ForegroundColor Red; exit 1 }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) { Write-Host "Nie znaleziono nvidia-smi (sterownik NVIDIA)." -ForegroundColor Red; exit 1 }

$vm = Get-Process -Name VBoxHeadless, VirtualBoxVM -ErrorAction SilentlyContinue
if ($vm) {
    Ostrz "Dzialaja maszyny wirtualne ($($vm.Count) proc.). Wylacz je przed pomiarem, bo zaburzaja wyniki."
    $odp = Read-Host "    Kontynuowac mimo to? [t/N]"
    if ($odp -notmatch '^[tTyY]') { exit 1 }
}

New-Item -ItemType Directory -Force $Folder | Out-Null
$log = Join-Path $Folder "gpu-log.csv"
$przebiegi = Join-Path $Folder "przebiegi.csv"
"tryb;proba;start;koniec" | Set-Content $przebiegi -Encoding UTF8

$czas = [math]::Round($Tryby.Count * $Proby * 0.6)
Info "Pomiar: $($Tryby.Count) trybow x $Proby prob (ok. $czas-$(2*$czas) min). Nie uzywaj w tym czasie karty graficznej."

# --- log karty w tle ---------------------------------------------------------
$argsSmi = "--query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.mem,power.draw,utilization.gpu --format=csv -l 2 -f `"$log`""
$logStart = (Get-Date).AddSeconds(-2)
$logger = Start-Process -FilePath $smi.Source -ArgumentList $argsSmi -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 6
if ($logger.HasExited -or -not (Test-Path $log)) { Write-Host "Log nvidia-smi nie wystartowal." -ForegroundColor Red; exit 1 }
Info "Log temperatury dziala: $log"

# --- pomiary -----------------------------------------------------------------
Push-Location $Hashcat
try {
    foreach ($m in $Tryby) {
        foreach ($i in 1..$Proby) {
            Write-Host ""
            Info "Tryb $m, proba $i z $Proby"
            $start = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $out = & $hcExe -b -m $m 2>&1 | ForEach-Object { "$_" }
            $koniec = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $out | Set-Content (Join-Path $Folder "bench-m$m-$i.txt") -Encoding UTF8
            "$m;$i;$start;$koniec" | Add-Content $przebiegi -Encoding UTF8
            $speed = $out | Where-Object { $_ -match 'Speed\.#' } | Select-Object -First 1
            if ($speed) { Write-Host "    $speed" } else { Ostrz "brak linii Speed - sprawdz plik bench-m$m-$i.txt" }
            Start-Sleep -Seconds 5   # chwila przerwy miedzy probami
        }
    }
}
finally {
    Pop-Location
    Start-Sleep -Seconds 4
    if (-not $logger.HasExited) { Stop-Process -Id $logger.Id -Force -ErrorAction SilentlyContinue }
    Get-Process -Name nvidia-smi -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -ge $logStart } | Stop-Process -Force -ErrorAction SilentlyContinue
}

# --- podsumowanie logu -------------------------------------------------------
Write-Host ""
Info "Podsumowanie logu karty"
$wiersze = Get-Content $log | Where-Object { $_ -and $_ -notmatch '^timestamp' }
$probki = foreach ($w in $wiersze) {
    $k = $w -split ','
    if ($k.Count -ge 6) {
        $num = { param($s) $v = ($s -replace '[^\d\.]', ''); if ($v) { [double]$v } else { $null } }
        [pscustomobject]@{
            Temp   = & $num $k[1]
            ZegarSM = & $num $k[2]
            Moc    = & $num $k[4]
            Obc    = & $num $k[5]
        }
    }
}
$pod = $probki | Where-Object { $_.Obc -ge 90 }
$lin = @()
$lin += "Probek w logu: $(@($probki).Count) (co 2 s), pod obciazeniem >= 90%: $(@($pod).Count)"
if ($pod) {
    $t = $pod | Measure-Object Temp -Average -Maximum
    $z = $pod | Measure-Object ZegarSM -Average -Minimum -Maximum
    $p = $pod | Measure-Object Moc -Average -Maximum
    $lin += "Temperatura GPU pod obciazeniem: srednio {0:N1} C, maks. {1:N0} C" -f $t.Average, $t.Maximum
    $lin += "Taktowanie SM pod obciazeniem:   srednio {0:N0} MHz, min. {1:N0} MHz, maks. {2:N0} MHz" -f $z.Average, $z.Minimum, $z.Maximum
    $lin += "Pobor mocy pod obciazeniem:      srednio {0:N1} W, maks. {1:N1} W" -f $p.Average, $p.Maximum
    if ($t.Maximum -ge 83) { $lin += "UWAGA: temperatura >= 83 C - mozliwe ograniczanie taktowania (throttling)." }
    else { $lin += "Temperatura ponizej progu ograniczania taktowania - brak wplywu termicznego na wyniki." }
}
$lin | ForEach-Object { Write-Host "    $_" }
$lin | Set-Content (Join-Path $Folder "log-podsumowanie.txt") -Encoding UTF8

# --- podsumowanie pomiarow ---------------------------------------------------
$pp = Join-Path $PSScriptRoot "podsumuj-pomiary.ps1"
Write-Host ""
if (Test-Path $pp) {
    Info "Podsumowanie pomiarow"
    & $pp -Folder $Folder
} else {
    Ostrz "Brak podsumuj-pomiary.ps1 obok tego skryptu - pomijam tabele wynikow."
}
Write-Host ""
Write-Host "Gotowe. Wgraj zawartosc folderu $Folder do repozytorium (wyniki/E4/pomiar1-powtorka)." -ForegroundColor Green
