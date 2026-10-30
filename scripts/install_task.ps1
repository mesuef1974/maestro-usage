# تثبيت مهمة مجدولة (للمستخدم الحالي فقط) لتشغيل src\run_cycle.py كل N دقيقة. التراجع: .\install_task.ps1 -Remove
param(
    [int]$EveryMinutes = 1,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$TaskName = "MaestroUsageIngest"
$Root = Split-Path -Parent $PSScriptRoot
$Pythonw = "C:\Users\mesue\AppData\Local\Programs\Python\Python312\pythonw.exe"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "removed $TaskName"
    exit 0
}

$action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('-I "{0}\src\run_cycle.py"' -f $Root) -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -ErrorAction Stop `
    -Description "maestro_usage incremental ingest of Claude Code usage logs (numbers only)" -Force | Out-Null
Write-Output "installed $TaskName every $EveryMinutes min"
