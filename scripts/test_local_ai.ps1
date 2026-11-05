# يشغّل اختبارات local_ai على قاعدة التطوير (المنفذ 5433) بقراءة DB_USER وDB_PASSWORD من .env دون عرضهما.
$Proj = "D:\shschool_mvp"
Set-Location $Proj
$env_ = @{}
Get-Content (Join-Path $Proj ".env") -Encoding UTF8 | ForEach-Object {
  if ($_ -match '^\s*(DB_USER|DB_PASSWORD)\s*=\s*(.*)$') { $env_[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'") }
}
if (-not $env_["DB_USER"]) { "لم أجد DB_USER في .env"; exit 1 }
$env:TEST_DB_PORT = "5433"
$env:TEST_DB_USER = $env_["DB_USER"]
$env:TEST_DB_PASSWORD = $env_["DB_PASSWORD"]
& (Join-Path $Proj ".venv\Scripts\python.exe") -m pytest tests/local_ai -q -p no:cacheprovider 2>&1 |
  Select-String -Pattern "passed|failed|^E  |^FAILED|^ERROR" | Select-Object -Last 40 | ForEach-Object { $_.Line }
