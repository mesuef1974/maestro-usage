# تشخيص حاويات التطوير: يكتب data\docker_diag.txt (سجلات وحالة) ولا يغيّر شيئًا.
$Root = Split-Path -Parent $PSScriptRoot
$F = Join-Path $Root "data\docker_diag.txt"
$o = @()
foreach ($c in "shschool-dev-web","shschool-dev-worker") {
  $o += "== $c"
  $o += (docker inspect $c --format "state={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} err={{.State.Error}}")
  $o += (docker logs --tail 60 $c 2>&1)
  $o += ""
}
$o += "== compose"
$o += (docker inspect shschool-dev-web --format "{{index .Config.Labels \"com.docker.compose.project.config_files\"}} | {{.Config.Cmd}}")
$o | Set-Content -Encoding UTF8 $F
"تم: $F"
