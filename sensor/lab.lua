-- Ustawienia laboratorium dla Snort 3, wczytywane jako "tweaks":
--   sudo cp lab.lua /usr/local/etc/snort/
--   sudo snort -c /usr/local/etc/snort/snort.lua --tweaks lab -i <interfejs> -A alert_fast
-- Plik jest wykonywany PO domyślnym snort.lua, więc nadpisuje wybrane moduły.

HOME_NET = '10.10.10.0/24'
-- default_variables powstaje w snort_defaults.lua przed tym plikiem, wiec aktualizujemy go recznie
if default_variables and default_variables.nets then
    default_variables.nets.HOME_NET = HOME_NET
end

-- Detekcja ARP spoofingu: znane powiązania IP <-> MAC w sieci laboratoryjnej.
-- Adresy MAC odczytane ze stanowiska (ip neigh na sensorze, 2026-10-25).
arp_spoof =
{
    hosts =
    {
        { ip = '10.10.10.20', mac = '08:00:27:3b:7f:6d' },  -- klient
        { ip = '10.10.10.30', mac = '08:00:27:f7:36:74' },  -- serwer
    }
}

-- Reguły wbudowane (m.in. alerty arp_spoof, gid 112) + reguły własne.
ips =
{
    enable_builtin_rules = true,
    variables = default_variables,
    include = '/usr/local/etc/rules/local.rules',
}
