$ErrorActionPreference = "Continue"
$log = Join-Path (Split-Path -Parent $PSScriptRoot) "datajb_admin.log"
"بدء " + (Get-Date -Format s) | Out-File $log -Encoding utf8
$un = "C:\Program Files (x86)\JetBrains\PyCharm 2024.3.5\bin\Uninstall.exe"
if (Test-Path $un) {
    $p = Start-Process -FilePath $un -ArgumentList "/S" -Wait -PassThru
    "PyCharm uninstall exit=" + $p.ExitCode | Out-File $log -Append -Encoding utf8
}
$m = Start-Process -FilePath "msiexec.exe" -ArgumentList "/x {0A7D7932-DB2D-4B36-AB71-D8F58FE2E4BF} /qn /norestart" -Wait -PassThru
"ETW msi exit=" + $m.ExitCode | Out-File $log -Append -Encoding utf8
Get-ScheduledTask | Where-Object { $_.TaskName -match "ETW Host Service Updater" } | Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
$svc = Get-Service | Where-Object { $_.Name -match "JetBrains" }
foreach ($s in $svc) { Stop-Service $s.Name -Force -ErrorAction SilentlyContinue; sc.exe delete $s.Name | Out-File $log -Append -Encoding utf8 }
Start-Sleep -Seconds 3
foreach ($d in @("C:\Program Files (x86)\JetBrains", "C:\Program Files\JetBrains", "C:\ProgramData\JetBrains")) {
    if (Test-Path $d) { Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; "حذف $d : " + (-not (Test-Path $d)) | Out-File $log -Append -Encoding utf8 }
}
foreach ($k in @("HKLM:\SOFTWARE\JetBrains", "HKLM:\SOFTWARE\WOW6432Node\JetBrains")) {
    if (Test-Path $k) { Remove-Item -LiteralPath $k -Recurse -Force -ErrorAction SilentlyContinue; "سجل $k : " + (-not (Test-Path $k)) | Out-File $log -Append -Encoding utf8 }
}
"انتهى" | Out-File $log -Append -Encoding utf8
