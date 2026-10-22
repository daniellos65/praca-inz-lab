<#
  podsumuj-pomiary.ps1 - zbiera wyniki testow wydajnosci Hashcata (tryb -b)

  Szuka plikow bench-m<TRYB>-<PROBA>.txt, wyciaga predkosc (Speed.#...),
  przelicza na H/s i liczy srednia, minimum, maksimum oraz odchylenie dla kazdego trybu.

  Uruchomienie:
      powershell -ExecutionPolicy Bypass -File .\podsumuj-pomiary.ps1
      powershell -ExecutionPolicy Bypass -File .\podsumuj-pomiary.ps1 -Folder F:\praca-inz\wyniki\E4

  Wyniki:
      - tabela na ekranie
      - <Folder>\podsumowanie.txt   (to samo co na ekranie)
      - <Folder>\wyniki-surowe.csv  (kazda proba osobno, do arkusza)
#>
param([string]$Folder = "F:\praca-inz\wyniki\E4")

$Nazwy = @{
    "0"     = "MD5"
    "1000"  = "NTLM"
    "11600" = "7-Zip"
    "13721" = "VeraCrypt SHA-512+AES"
    "13400" = "KeePass KDBX 3.1 (AES-KDF)"
    "34300" = "KeePass KDBX4 (Argon2)"
}
$Mnoznik = @{ "H/s" = 1; "kH/s" = 1e3; "MH/s" = 1e6; "GH/s" = 1e9; "TH/s" = 1e12 }

$pliki = Get-ChildItem -Path $Folder -Filter "bench-m*-*.txt" | Where-Object { $_.BaseName -match '^bench-m(\d+)-(\d+)$' }
if (-not $pliki) { Write-Host "Brak plikow bench-m<tryb>-<proba>.txt w $Folder" -ForegroundColor Red; exit 1 }

$proby = foreach ($p in $pliki) {
    $null = $p.BaseName -match '^bench-m(\d+)-(\d+)$'
    $tryb = $matches[1]; $nr = [int]$matches[2]
    $tekst = Get-Content $p.FullName -Raw
    if ($tekst -match 'Speed\.#[\d\*]+\.*:\s+([\d\.]+)\s+([kMGT]?H/s)') {
        [pscustomobject]@{ Tryb = $tryb; Proba = $nr; HS = [double]$matches[1] * $Mnoznik[$matches[2]] }
    } else {
        Write-Host "Brak predkosci w pliku $($p.Name) - pomiar nieudany lub przerwany" -ForegroundColor Yellow
    }
}

$proby | Sort-Object { [int]$_.Tryb }, Proba |
    Select-Object Tryb, @{ n = "Algorytm"; e = { $Nazwy[$_.Tryb] } }, Proba, HS |
    Export-Csv -Path (Join-Path $Folder "wyniki-surowe.csv") -NoTypeInformation -Encoding UTF8 -Delimiter ";"

$md5 = ($proby | Where-Object Tryb -eq "0" | Measure-Object HS -Average).Average

$linie = @()
$linie += "{0,-6} {1,-28} {2,18} {3,4} {4,8} {5,14}" -f "Tryb", "Algorytm", "Srednia [H/s]", "n", "Odch.%", "Wolniej niz MD5"
foreach ($g in ($proby | Group-Object Tryb | Sort-Object { [int]$_.Name })) {
    $hs = $g.Group.HS
    $sr = ($hs | Measure-Object -Average).Average
    $odch = 0
    if ($hs.Count -gt 1) { $odch = [math]::Sqrt((($hs | ForEach-Object { ($_ - $sr) * ($_ - $sr) }) | Measure-Object -Sum).Sum / ($hs.Count - 1)) / $sr * 100 }
    $razy = ""
    if ($md5 -and $sr -gt 0) { $r = $md5 / $sr; if ($r -lt 10) { $razy = "{0:N2}x" -f $r } else { $razy = "{0:N0}x" -f $r } }
    $linie += "{0,-6} {1,-28} {2,18:N0} {3,4} {4,7:N1}% {5,14}" -f $g.Name, $Nazwy[$g.Name], $sr, $g.Count, $odch, $razy
}

$linie | ForEach-Object { Write-Host $_ }
$linie | Set-Content -Path (Join-Path $Folder "podsumowanie.txt") -Encoding UTF8
Write-Host ""
Write-Host "Zapisano: podsumowanie.txt i wyniki-surowe.csv w $Folder" -ForegroundColor Green
