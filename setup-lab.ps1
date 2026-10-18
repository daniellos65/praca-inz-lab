<#
  setup-lab.ps1 - automatyczna konfiguracja laboratorium w VirtualBox

  Uruchomienie (PowerShell, w rozpakowanym folderze lab):
      powershell -ExecutionPolicy Bypass -File .\setup-lab.ps1

  Co robi:
    1. Sprawdza VirtualBox, maszyne bazowa i wolne miejsce na dysku.
    2. Usuwa niedzialajace klony client/server/sensor (po potwierdzeniu).
    3. Tworzy klony POLACZONE (malo miejsca) z migawki "czysta-baza".
    4. Ustawia siec: karta 1 = labnet, karta 2 = NAT z przekierowaniem SSH:
         server -> localhost:2230, client -> localhost:2220, sensor -> localhost:2240
    5. Uruchamia maszyny w tle, instaluje klucz SSH, przesyla folder lab.
    6. W kazdej maszynie uruchamia vm-bootstrap.sh (nazwa, adres, rola).
    7. Sprawdza pingi miedzy maszynami i dopisuje skroty do ~/.ssh/config
       (ssh lab-server, ssh lab-client, ssh lab-sensor).

  Hasla: kazda maszyna zapyta 2 razy o haslo uzytkownika Ubuntu
  (raz przy instalacji klucza SSH, raz dla sudo).

  Opcje:
    -BaseVm nazwa   maszyna bazowa (domyslnie ubuntu-base)
    -User nazwa     uzytkownik w Ubuntu (domyslnie pyta)
    -GuestOnly      pomija VirtualBox, konfiguruje tylko wnetrze istniejacych maszyn
    -NoRoles        nie instaluje Dockera/OpenSSL/Snorta
    -Yes            nie pyta o potwierdzenie usuniecia klonow
#>
param(
    [string]$BaseVm = "ubuntu-base",
    [string]$User,
    [switch]$GuestOnly,
    [switch]$NoRoles,
    [switch]$Yes
)

$ErrorActionPreference = "Continue"
$LabDir = $PSScriptRoot
$SnapshotName = "czysta-baza"

$Vms = @(
    @{ Name = "server"; Ip = "10.10.10.30"; Port = 2230; Mem = 2048; Cpus = 2; Promisc = "deny" },
    @{ Name = "client"; Ip = "10.10.10.20"; Port = 2220; Mem = 1024; Cpus = 1; Promisc = "deny" },
    @{ Name = "sensor"; Ip = "10.10.10.40"; Port = 2240; Mem = 4096; Cpus = 2; Promisc = "allow-all" }
)

# ---------------------------------------------------------------------------
# Funkcje pomocnicze
# ---------------------------------------------------------------------------
function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "    [OK] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    [!] $text" -ForegroundColor Yellow }
function Fail($text) { throw $text }

function Find-VBoxManage {
    $candidates = @($env:VBOX_MSI_INSTALL_PATH, $env:VBOX_INSTALL_PATH, "C:\Program Files\Oracle\VirtualBox")
    foreach ($p in $candidates) {
        if ($p -and (Test-Path (Join-Path $p "VBoxManage.exe"))) { return (Join-Path $p "VBoxManage.exe") }
    }
    return $null
}

function VBox {
    $out = & $script:VBM @args 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { Fail ("VBoxManage " + ($args -join " ") + "`n" + ($out -join "`n")) }
    return $out
}

function VBoxTry {
    & $script:VBM @args 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Get-VmNames {
    $names = @()
    foreach ($line in (VBox list vms)) {
        if ($line -match '^"(.+)" \{') { $names += $matches[1] }
    }
    return $names
}

function Get-VmInfo($name) {
    $h = @{}
    foreach ($line in (VBox showvminfo $name --machinereadable)) {
        if ($line -match '^"?([^"=]+)"?="?(.*?)"?$') { $h[$matches[1]] = $matches[2] }
    }
    return $h
}

function Format-Mac($raw) {
    # "0800271A2B3C" -> "08:00:27:1a:2b:3c"
    $raw = $raw.ToLower()
    return (($raw -split '(..)' | Where-Object { $_ }) -join ':')
}

function Get-DefaultMachineFolder {
    foreach ($line in (VBox list systemproperties)) {
        if ($line -match '^Default machine folder:\s+(.+)$') { return $matches[1].Trim() }
    }
    return (Join-Path $HOME "VirtualBox VMs")
}

function Wait-VmState($name, $state, $timeoutSec = 120) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        if ((Get-VmInfo $name)["VMState"] -eq $state) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

# --- SSH --------------------------------------------------------------------
$Key = Join-Path $HOME ".ssh\lab_ed25519"
$script:KnownHosts = $null

function New-KnownHostsFile {
    # Katalog bez spacji (ssh dzieli wartosc UserKnownHostsFile na spacjach)
    $dir = Join-Path $env:PUBLIC "lab-ssh"
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $script:KnownHosts = Join-Path $dir ("known_hosts_" + [guid]::NewGuid().ToString("N"))
}

function SshOpts($port) {
    return @("-p", "$port", "-i", $Key,
             "-o", "StrictHostKeyChecking=no",
             "-o", "UserKnownHostsFile=$($script:KnownHosts)",
             "-o", "LogLevel=ERROR",
             "-o", "ConnectTimeout=8")
}

# Zwraca "key" (logowanie kluczem dziala), "password" (SSH dziala, klucza brak) lub $null
function Test-Ssh($port) {
    $o = SshOpts $port
    $out = & ssh @o -o BatchMode=yes "$User@127.0.0.1" "true" 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -eq 0) { return "key" }
    if (($out -join " ") -match "Permission denied") { return "password" }
    return $null
}

function Wait-Ssh($port, $timeoutSec = 300) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        $r = Test-Ssh $port
        if ($r) { return $r }
        Start-Sleep -Seconds 5
    }
    return $null
}

# Wynik trafia na konsole; kod wyjscia w $script:SshExit
function Invoke-Ssh($port, [string]$command, [switch]$Tty) {
    $opts = SshOpts $port
    if ($Tty) { $opts += "-t" }
    & ssh @opts "$User@127.0.0.1" $command | Out-Host
    $script:SshExit = $LASTEXITCODE
}

# ---------------------------------------------------------------------------
try {
    Step "Sprawdzanie narzedzi"
    $script:VBM = Find-VBoxManage
    if (-not $VBM) { Fail "Nie znaleziono VBoxManage.exe. Czy VirtualBox jest zainstalowany?" }
    Ok ("VirtualBox " + ((VBox --version) -join ""))
    foreach ($tool in @("ssh", "scp", "ssh-keygen", "tar")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Fail "Brak polecenia '$tool'. Wlacz klienta OpenSSH: Ustawienia > Aplikacje > Funkcje opcjonalne > Klient OpenSSH."
        }
    }
    Ok "ssh, scp, ssh-keygen, tar"
    foreach ($f in @("vm-bootstrap.sh", "vm-roles.sh", "server", "client", "sensor")) {
        if (-not (Test-Path (Join-Path $LabDir $f))) { Fail "Brak '$f' w $LabDir. Uruchom skrypt z rozpakowanego folderu lab." }
    }
    Ok "pliki laboratorium w $LabDir"

    if (-not $User) {
        $User = Read-Host "Nazwa uzytkownika w Ubuntu (Enter = student)"
        if (-not $User) { $User = "student" }
    }

    $hostRamGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    Ok "RAM komputera: $hostRamGb GB"
    if ($hostRamGb -lt 12) {
        Warn "Malo RAM - czujnik dostanie 3 GB zamiast 4 GB."
        $Vms[2].Mem = 3072
    }

    if (-not $GuestOnly) {
        # ---------------------------------------------------------------
        Step "Maszyna bazowa '$BaseVm'"
        $names = Get-VmNames
        if ($names -notcontains $BaseVm) { Fail "Nie ma maszyny '$BaseVm'. Dostepne: $($names -join ', ')" }
        $baseInfo = Get-VmInfo $BaseVm
        $state = $baseInfo["VMState"]
        if ($state -notin @("poweroff", "aborted")) {
            Fail "Maszyna '$BaseVm' ma stan '$state'. Wylacz ja (w Ubuntu: sudo poweroff) i uruchom skrypt ponownie."
        }
        Ok "stan: $state"

        # ---------------------------------------------------------------
        Step "Wolne miejsce na dysku"
        $vmFolder = Get-DefaultMachineFolder
        $drive = [System.IO.Path]::GetPathRoot($vmFolder)
        $freeGb = [math]::Round((New-Object System.IO.DriveInfo $drive).AvailableFreeSpace / 1GB, 1)
        Ok "folder maszyn: $vmFolder (dysk $drive, wolne $freeGb GB)"

        # ---------------------------------------------------------------
        Step "Sprzatanie starych klonow"
        $toDelete = @()
        foreach ($vm in $Vms) {
            if ($names -contains $vm.Name) { $toDelete += "maszyna '$($vm.Name)'" }
            elseif (Test-Path (Join-Path $vmFolder $vm.Name)) { $toDelete += "folder '$(Join-Path $vmFolder $vm.Name)'" }
        }
        if ($toDelete.Count -gt 0) {
            Write-Host "    Zostana usuniete (razem z dyskami):"
            $toDelete | ForEach-Object { Write-Host "      - $_" }
            Write-Host "    Maszyna bazowa '$BaseVm' NIE zostanie ruszona."
            if (-not $Yes) {
                $ans = Read-Host "    Kontynuowac? [t/N]"
                if ($ans -notmatch '^[tTyY]') { Fail "Przerwano na zyczenie uzytkownika." }
            }
            foreach ($vm in $Vms) {
                if ($names -contains $vm.Name) {
                    $st = (Get-VmInfo $vm.Name)["VMState"]
                    if ($st -in @("running", "paused", "stuck")) {
                        VBoxTry controlvm $vm.Name poweroff | Out-Null
                        Wait-VmState $vm.Name "poweroff" 60 | Out-Null
                    }
                    if ($st -eq "saved") { VBoxTry discardstate $vm.Name | Out-Null }
                    VBox unregistervm $vm.Name --delete | Out-Null
                }
                $folder = Join-Path $vmFolder $vm.Name
                if (Test-Path $folder) { Remove-Item -Recurse -Force $folder }
            }
            # niedostepne dyski po nieudanych klonach
            $block = @{}
            foreach ($line in (@(VBox list hdds) + @(""))) {
                if ($line -match '^(UUID|State|Location):\s+(.+)$') { $block[$matches[1]] = $matches[2].Trim() }
                elseif ($line -eq "" -and $block.Count -gt 0) {
                    if ($block["State"] -eq "inaccessible" -and $block["Location"] -like "$vmFolder*") {
                        foreach ($vm in $Vms) {
                            if ($block["Location"] -like (Join-Path $vmFolder "$($vm.Name)\*")) {
                                VBoxTry closemedium disk $block["UUID"] | Out-Null
                                Ok "wyrejestrowano niedostepny dysk $($block['Location'])"
                            }
                        }
                    }
                    $block = @{}
                }
            }
            $freeGb = [math]::Round((New-Object System.IO.DriveInfo $drive).AvailableFreeSpace / 1GB, 1)
            Ok "usunieto; wolne miejsce: $freeGb GB"
        } else {
            Ok "brak starych klonow"
        }

        if ($freeGb -lt 8) {
            Fail "Za malo miejsca ($freeGb GB). Potrzeba min. 8 GB, zalecane 20 GB. Zwolnij miejsce albo zmien folder maszyn w VirtualBox (Plik > Preferencje > Ogolne)."
        }
        if ($freeGb -lt 20) { Warn "Wolne $freeGb GB - wystarczy na start, ale Docker i Snort zajma razem ok. 10 GB." }

        # ---------------------------------------------------------------
        Step "Migawka '$SnapshotName' maszyny bazowej"
        $baseInfo = Get-VmInfo $BaseVm
        $hasSnap = $false
        foreach ($k in $baseInfo.Keys) { if ($k -like "SnapshotName*" -and $baseInfo[$k] -eq $SnapshotName) { $hasSnap = $true } }
        if ($hasSnap) { Ok "juz istnieje" }
        else {
            VBox snapshot $BaseVm take $SnapshotName --description "Baza dla klonow polaczonych - nie usuwac" | Out-Null
            Ok "utworzona"
        }

        # ---------------------------------------------------------------
        Step "Tworzenie klonow polaczonych"
        foreach ($vm in $Vms) {
            VBox clonevm $BaseVm --snapshot $SnapshotName --options=Link --name $vm.Name --register | Out-Null
            VBox modifyvm $vm.Name --memory $vm.Mem --cpus $vm.Cpus `
                --nic1 intnet --intnet1 labnet --nicpromisc1 $vm.Promisc --cableconnected1 on `
                --nic2 nat --cableconnected2 on | Out-Null
            VBoxTry modifyvm $vm.Name --natpf2 delete ssh | Out-Null
            VBox modifyvm $vm.Name --natpf2 "ssh,tcp,127.0.0.1,$($vm.Port),,22" | Out-Null
            VBoxTry modifyvm $vm.Name --groups "/Laboratorium" | Out-Null
            Ok "$($vm.Name): $($vm.Mem) MB RAM, $($vm.Cpus) vCPU, SSH localhost:$($vm.Port), nasluch: $($vm.Promisc)"
        }
        VBoxTry modifyvm $BaseVm --groups "/Laboratorium" | Out-Null
    }

    # -------------------------------------------------------------------
    Step "Uruchamianie maszyn (w tle)"
    $names = Get-VmNames
    foreach ($vm in $Vms) {
        if ($names -notcontains $vm.Name) { Fail "Brak maszyny '$($vm.Name)'. Uruchom skrypt bez -GuestOnly." }
        $info = Get-VmInfo $vm.Name
        $vm.LabMac = Format-Mac $info["macaddress1"]
        if ($info["VMState"] -ne "running") {
            VBox startvm $vm.Name --type headless | Out-Null
            Ok "$($vm.Name) uruchomiona (MAC labnet $($vm.LabMac))"
        } else {
            Ok "$($vm.Name) juz dziala (MAC labnet $($vm.LabMac))"
        }
    }

    # -------------------------------------------------------------------
    Step "Klucz SSH"
    if (-not (Test-Path $Key)) {
        New-Item -ItemType Directory -Force (Split-Path $Key) | Out-Null
        Start-Process ssh-keygen -ArgumentList "-q -t ed25519 -N `"`" -C lab-inz -f `"$Key`"" -NoNewWindow -Wait
        Ok "utworzono $Key"
    } else { Ok "istnieje $Key" }
    $pub = (Get-Content "$Key.pub" -Raw).Trim()

    $tar = Join-Path $env:TEMP "lab-upload.tar"
    if (Test-Path $tar) { Remove-Item -Force $tar }
    & tar -C $LabDir -cf $tar .
    if ($LASTEXITCODE -ne 0) { Fail "Nie udalo sie spakowac folderu lab" }

    $clientMac = ($Vms | Where-Object { $_.Name -eq "client" }).LabMac
    $serverMac = ($Vms | Where-Object { $_.Name -eq "server" }).LabMac

    foreach ($vm in $Vms) {
        New-KnownHostsFile
        Step "Konfiguracja wnetrza: $($vm.Name)"
        Write-Host "    czekam na SSH (localhost:$($vm.Port))..."
        $auth = Wait-Ssh $vm.Port 300
        if (-not $auth) { Fail "$($vm.Name): SSH nie odpowiada po 5 min. Otworz okno maszyny w VirtualBox i sprawdz, czy system wystartowal." }

        if ($auth -eq "password") {
            Write-Host "    instalacja klucza SSH - podaj haslo uzytkownika $User" -ForegroundColor Yellow
            $cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && (grep -qxF '$pub' ~/.ssh/authorized_keys || echo '$pub' >> ~/.ssh/authorized_keys) && chmod 600 ~/.ssh/authorized_keys"
            Invoke-Ssh $vm.Port $cmd
            if ($script:SshExit -ne 0) { Fail "$($vm.Name): nie udalo sie zainstalowac klucza (zle haslo lub uzytkownik?)" }
        }
        Ok "logowanie kluczem dziala"

        $so = @(SshOpts $vm.Port | ForEach-Object { if ($_ -eq "-p") { "-P" } else { $_ } })
        & scp @so $tar "$User@127.0.0.1:/tmp/lab-upload.tar"
        if ($LASTEXITCODE -ne 0) { Fail "$($vm.Name): blad przesylania plikow" }
        Invoke-Ssh $vm.Port "rm -rf ~/lab && mkdir -p ~/lab && tar -xf /tmp/lab-upload.tar -C ~/lab && rm -f /tmp/lab-upload.tar"
        if ($script:SshExit -ne 0) {
            Fail "$($vm.Name): blad rozpakowania plikow"
        }
        Ok "pliki laboratorium w ~/lab"

        $bootArgs = "--role $($vm.Name) --ip $($vm.Ip) --lab-mac $($vm.LabMac)"
        if ($vm.Name -eq "sensor") { $bootArgs += " --client-mac $clientMac --server-mac $serverMac" }
        if ($NoRoles) { $bootArgs += " --no-roles" }
        Write-Host "    vm-bootstrap.sh - podaj haslo dla sudo, jesli zapyta" -ForegroundColor Yellow
        Invoke-Ssh $vm.Port "sudo bash ~/lab/vm-bootstrap.sh $bootArgs" -Tty
        if ($script:SshExit -ne 0) {
            Fail "$($vm.Name): vm-bootstrap.sh zakonczyl sie bledem (komunikat powyzej)"
        }
        if (Test-Path $script:KnownHosts) { Remove-Item -Force $script:KnownHosts }
    }
    Remove-Item -Force $tar -ErrorAction SilentlyContinue

    # -------------------------------------------------------------------
    Step "Test sieci labnet (ping miedzy maszynami)"
    New-KnownHostsFile
    $allOk = $true
    foreach ($vm in $Vms) {
        foreach ($other in ($Vms | Where-Object { $_.Name -ne $vm.Name })) {
            $o = SshOpts $vm.Port
            $null = & ssh @o -o BatchMode=yes "$User@127.0.0.1" "ping -c 2 -W 2 $($other.Ip)" 2>&1
            if ($LASTEXITCODE -eq 0) { Ok "$($vm.Name) -> $($other.Name) ($($other.Ip))" }
            else { Warn "$($vm.Name) -> $($other.Name) ($($other.Ip)): BRAK ODPOWIEDZI"; $allOk = $false }
        }
    }
    if (Test-Path $script:KnownHosts) { Remove-Item -Force $script:KnownHosts }

    # -------------------------------------------------------------------
    Step "Skroty SSH w ~/.ssh/config"
    $cfgPath = Join-Path $HOME ".ssh\config"
    $labKnown = Join-Path $HOME ".ssh\lab_known_hosts"
    if (Test-Path $labKnown) { Remove-Item -Force $labKnown }   # klucze hostow zmieniaja sie po kazdym klonowaniu
    $block = "# >>> lab-inz (setup-lab.ps1)`n"
    foreach ($vm in $Vms) {
        $block += "Host lab-$($vm.Name)`n  HostName 127.0.0.1`n  Port $($vm.Port)`n  User $User`n  IdentityFile ~/.ssh/lab_ed25519`n  StrictHostKeyChecking accept-new`n  UserKnownHostsFile ~/.ssh/lab_known_hosts`n"
    }
    $block += "# <<< lab-inz`n"
    $cfg = ""
    if (Test-Path $cfgPath) { $cfg = [IO.File]::ReadAllText($cfgPath) }
    $cfg = [regex]::Replace($cfg, '(?s)# >>> lab-inz.*?# <<< lab-inz\r?\n?', '')
    if ($cfg -and -not $cfg.EndsWith("`n")) { $cfg += "`n" }
    [IO.File]::WriteAllText($cfgPath, $cfg + $block, (New-Object System.Text.UTF8Encoding $false))
    Ok "ssh lab-server | ssh lab-client | ssh lab-sensor"

    # -------------------------------------------------------------------
    Step "Podsumowanie"
    if ($allOk) { Ok "Siec labnet dziala miedzy wszystkimi maszynami." }
    else { Warn "Czesc pingow nie przeszla - wklej ten wynik do rozmowy." }
    if (-not $NoRoles) {
        Write-Host ""
        Write-Host "    Instalacja oprogramowania trwa W TLE w maszynach:"
        Write-Host "      server: Docker + uslugi laboratorium   ok. 10 min"
        Write-Host "      client: OpenSSL 1.0.2u                 ok. 10 min"
        Write-Host "      sensor: kompilacja Snort 3              30-60 min"
        Write-Host ""
        Write-Host "    Postep:  ssh lab-sensor `"sudo tail -f /var/log/lab-role.log`""
        Write-Host "    Gotowe, gdy w logu jest linia 'KONIEC: rola ... - OK'."
    }
    Write-Host ""
    Write-Host "    Maszyny dzialaja w tle (bez okien). Podglad: VirtualBox > maszyna > Pokaz."
    Write-Host "    Nie usuwaj maszyny '$BaseVm' ani jej migawki '$SnapshotName' - klony z nich korzystaja."
}
catch {
    Write-Host ""
    Write-Host "BLAD: $_" -ForegroundColor Red
    Write-Host "Wklej ten komunikat do rozmowy. Skrypt mozna uruchomic ponownie." -ForegroundColor Red
    exit 1
}
