# تنظيف دوكر بعد اعتماد جلسة واحدة: افتراضيًّا يعرض فقط ولا يحذف شيئًا، ويكتب تقريرًا في data\docker_cleanup_report.txt.
# الاستعمال:  .\docker_cleanup.ps1            (عرض فقط)
#             .\docker_cleanup.ps1 -Apply     (ينفّذ)
#             .\docker_cleanup.ps1 -Apply -Images   (ويحذف أيضًا كل صورة لا تستعملها حاوية الآن)
# مع -Apply يُحذف: حاويات الجلسات القديمة (اسمها يبدأ بـ schoolos- عدا schoolos-main-preview)، والحاويات المتوقفة،
#   والصور التي صارت بلا حاوية، ووحدات التخزين المجهولة (اسمها 64 خانة سداسية عشرية) غير المستعملة، وذاكرة البناء المعلَّقة.
# لا يمسّ أبدًا: shschool-dev-* (قاعدة التطوير وردس)، ومعاينة schoolos-main-preview*، ولا أي وحدة تخزين مسمّاة (مثل shschool_mvp_shschool_pgdata18).
param([switch]$Apply, [switch]$Images)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Report = Join-Path $Root "data\docker_cleanup_report.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $Report) | Out-Null
$out = New-Object System.Collections.Generic.List[string]
function Add-Section($title, $lines) { $out.Add("== $title"); foreach ($l in $lines) { $out.Add([string]$l) }; $out.Add("") }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { "docker غير موجود في PATH" | Set-Content -Encoding UTF8 $Report; exit 1 }
$fmt = "{{.Names}} | {{.Image}} | {{.Status}}"
$all = @(docker ps -a --format "{{.Names}}")
$sessions = @($all | Where-Object { $_ -match "^schoolos-" -and $_ -notmatch "^schoolos-main-preview" })
$keep = @($all | Where-Object { $sessions -notcontains $_ })
$anon = @(docker volume ls -q --filter dangling=true | Where-Object { $_ -match "^[0-9a-f]{64}$" })

Add-Section "تبقى كما هي (معاينة وتطوير وغيرها)" $keep
Add-Section "حاويات الجلسات القديمة (تُحذف مع -Apply، تعمل أو متوقفة)" $sessions
Add-Section "وحدات تخزين مجهولة غير مستعملة (تُحذف مع -Apply)" @("العدد: $($anon.Count)")
Add-Section "استهلاك المساحة قبل" (docker system df)

if ($Apply) {
    if ($sessions.Count) { Add-Section "حذف حاويات الجلسات" (docker rm -f $sessions) }
    Add-Section "حذف الحاويات المتوقفة" (docker container prune -f)
    Add-Section "حذف الصور بلا حاوية" (docker image prune -f)
    $anon2 = @(docker volume ls -q --filter dangling=true | Where-Object { $_ -match "^[0-9a-f]{64}$" })
    if ($anon2.Count) { Add-Section "حذف وحدات التخزين المجهولة" (docker volume rm $anon2) }
    if ($Images) { Add-Section "حذف كل الصور غير المستعملة" (docker image prune -a -f) }
    Add-Section "حذف ذاكرة البناء المعلَّقة" (docker builder prune -f)
    Add-Section "المساحة بعد" (docker system df)
    Add-Section "الحاويات الباقية" (docker ps -a --format $fmt)
} else { $out.Add("عرض فقط: لم يُحذف شيء. أضف -Apply للتنفيذ.") }
$out | Set-Content -Encoding UTF8 $Report
$out
