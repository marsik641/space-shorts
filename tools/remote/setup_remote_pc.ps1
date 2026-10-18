# Настройка ПК для удалённого рендера Orbitfall (Windows 10/11). Запускать ОДИН РАЗ в PowerShell от администратора:
#   powershell -ExecutionPolicy Bypass -File setup_remote_pc.ps1            (рабочая папка D:\orbitfall)
#   powershell -ExecutionPolicy Bypass -File setup_remote_pc.ps1 -Root E:\orbitfall
# Что делает (и ничего больше):
#   1) включает встроенный в Windows OpenSSH Server (служба sshd, автозапуск, правило брандмауэра на порт 22);
#   2) добавляет ОДИН публичный ключ (ниже) — вход по ssh только с этим ключом, пароль не передаётся;
#   3) создаёт рабочую папку (по умолчанию D:\orbitfall: код, кадры ~7 ГБ на ролик, логи);
#   4) печатает: имя пользователя, адрес Tailscale, Python, Blender, видеокарту, свободное место.
# Отменить: удалить строку ключа из двух файлов, которые назовёт скрипт, и/или остановить службу:
#   Stop-Service sshd; Set-Service sshd -StartupType Disabled
param([string]$Root = "D:\orbitfall")
$ErrorActionPreference = "Stop"
$PubKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICVV4w6ZpFmALJGGddkzpJROL/ogdLRJ+pDOe8Xwzhm7 orbitfall-render"

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Запустите PowerShell от имени администратора." -ForegroundColor Red; exit 1
}

# 1) OpenSSH Server
$cap = Get-WindowsCapability -Online | Where-Object Name -like "OpenSSH.Server*"
if ($cap.State -ne "Installed") {
    Write-Host "Устанавливаю OpenSSH Server..."
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
}
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
if (-not (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True `
        -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}

# 2) ключ — в оба файла, где его ищет sshd: для учёток-администраторов Windows OpenSSH читает только
#    C:\ProgramData\ssh\administrators_authorized_keys, для обычных — ~\.ssh\authorized_keys
$user = $env:USERNAME
$adminKeys = Join-Path $env:ProgramData "ssh\administrators_authorized_keys"
New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE ".ssh") | Out-Null
$userKeys = Join-Path $env:USERPROFILE ".ssh\authorized_keys"
foreach ($keyFile in @($adminKeys, $userKeys)) {
    if (-not (Test-Path $keyFile) -or -not (Select-String -Path $keyFile -SimpleMatch $PubKey -Quiet)) {
        Add-Content -Path $keyFile -Value $PubKey -Encoding ascii
    }
}
# права, без которых sshd игнорирует файл администраторов: только SYSTEM и группа Администраторы (SID)
icacls.exe $adminKeys /inheritance:r /grant "*S-1-5-32-544:F" /grant "*S-1-5-18:F" | Out-Null

# 3) рабочая папка
New-Item -ItemType Directory -Force $Root | Out-Null

# 4) сводка — только чтение, ошибки отдельных проверок не прерывают её
$ErrorActionPreference = "Continue"
Write-Host ""
Write-Host "=== Готово. Пришлите владельцу рендера эти строки ===" -ForegroundColor Green
Write-Host "user:      $user"
Write-Host "computer:  $env:COMPUTERNAME"
Write-Host "root:      $Root"
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts -and (Test-Path "C:\Program Files\Tailscale\tailscale.exe")) { $ts = "C:\Program Files\Tailscale\tailscale.exe" }
if ($ts) {
    Write-Host "tailscale: $(& $ts ip -4 2>$null)"
    # UDP / IPv4 / ближайший DERP: если UDP false или DERP пуст — трафик Tailscale глотает прокси (TUN)
    & $ts netcheck 2>$null | Select-String "UDP:|IPv4:|Nearest DERP" | ForEach-Object { Write-Host "  netcheck $($_.Line.Trim())" }
} else { Write-Host "tailscale: НЕ УСТАНОВЛЕН (https://tailscale.com/download)" -ForegroundColor Yellow }
# python: через cmd — stderr не превращается в ошибку PowerShell; заглушка Microsoft Store (WindowsApps) не годится
foreach ($name in @("python", "py")) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $c) { Write-Host "${name}:    не найден в PATH" -ForegroundColor Yellow; continue }
    $ver = (cmd /c "$name --version 2>&1" | Out-String).Trim()
    $note = if ($c.Source -like "*WindowsApps*") { "  <- заглушка Microsoft Store, нужен Python с python.org" } else { "" }
    Write-Host "${name}:    $($c.Source) ($ver)$note"
}
$bl = @()
foreach ($d in (Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -ne $null })) {
    foreach ($pat in @("Program Files\Blender Foundation\Blender *\blender.exe", "Blender*\blender.exe",
                       "SteamLibrary\steamapps\common\Blender\blender.exe", "Program Files (x86)\Steam\steamapps\common\Blender\blender.exe")) {
        $bl += Get-ChildItem (Join-Path $d.Root $pat) -ErrorAction SilentlyContinue
    }
}
if ($bl) { $bl | ForEach-Object { Write-Host "blender:   $($_.FullName)" } } else { Write-Host "blender:   не найден (пришлите путь к blender.exe)" -ForegroundColor Yellow }
Get-CimInstance Win32_VideoController | ForEach-Object { Write-Host "gpu:       $($_.Name) (драйвер $($_.DriverVersion))" }
$drv = (Get-Item $Root).PSDrive
Write-Host ("disk {0}:   свободно {1:N0} ГБ (нужно ~15)" -f $drv.Name, ($drv.Free / 1GB))
Write-Host "key files: $adminKeys ; $userKeys"
