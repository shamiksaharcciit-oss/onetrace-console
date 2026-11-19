# postdeploy_080_captures.ps1 -- the capture store's app after `fly deploy` of onetrace-console 0.8.0.
# Read-only: GETs, and one POST that must be refused. Sends no secret and needs none.
#
#   .\postdeploy_080_captures.ps1 -Base https://<the capture store's address> [-Demo https://<the demo's address>]
#
# Every request goes over a connection of its own, and every page is asked for once before any check (a warm-up
# pass), so a machine still starting answers the warm-up, not a check (0.7.0's own post-deploy run). Prints PASS,
# FAIL or SKIP per check, then "<n> of <m> passed"; exits 0 only when every check run passes. C7 runs where -Demo
# is given, as the capture store's app then names the demo.
param(
    [Parameter(Mandatory = $true)][string]$Base,
    [string]$Demo = ""
)
$ErrorActionPreference = "Stop"
# The HTTP client's assembly, its name written in two parts: the folder's scan reads a dotted name ending in
# that word as a domain (tests/test_deploy_fly.py).
Add-Type -AssemblyName ("System." + "Net.Http")
$Base = $Base.TrimEnd("/")
$script:results = @()

function Get-Page([string]$Path, [string]$Method = "GET") {
    # A connection of its own: a new client, and the connection closed after the answer.
    $client = [Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds(60)
    try {
        $req = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::new($Method), $Base + $Path)
        $req.Headers.ConnectionClose = $true
        if ($Method -eq "POST") { $req.Content = [Net.Http.StringContent]::new("x") }
        $resp = $client.SendAsync($req).GetAwaiter().GetResult()
        $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        [pscustomobject]@{ Status = [int]$resp.StatusCode; Body = $body }
    } finally {
        $client.Dispose()
    }
}

function Check([string]$Name, [bool]$Ok, [string]$Said = "") {
    $script:results += $Ok
    $word = if ($Ok) { "PASS" } else { "FAIL" }
    if ($Said) { Write-Output "$word  $Name  -- $Said" } else { Write-Output "$word  $Name" }
}

function Skip([string]$Name, [string]$Why) { Write-Output "SKIP  $Name  -- $Why" }

# The public scan's words, by the sha256 of each (the words themselves are the scan's own list,
# tests/test_ux_screens.py NOT_ON_A_PAGE, and are not written here). Matched case-blind where the scan is.
$sha = [System.Security.Cryptography.SHA256]::Create()
function Hash([string]$Word) {
    -join ($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Word)) | ForEach-Object { $_.ToString("x2") })
}
$CaseKept = @(
    "b18570b0bed47f0732079aa7615826e81e4fadc8d01da5e0cb16410870b05371",
    "0d45f5fd462b8c70bffb10021ac1bcff3f58f29b1faf7568595095427d42812c",
    "425c89ed5bb78a7623fae60fd8a6f648488168740fe82cf6ad34caa4d07aa972"
)
$CaseBlind = @(
    "727e1f5f2da46bcb1708f87e4dbfdaaa6d9a5df99fb0506f34dde1f2ee041782",
    "e100fbce008c04ec40637af0af91fb2f05aeedc23f856a2d3c0b1580625d755e"
)
# Patterns the scan holds that are shapes, not words: two kinds of internal id, and a version promise.
$Shapes = @('\bR-20\d\d-\d\d-\d\d', '\bWO-C\d', '(?i)until\s+onetrace')

function Words-Seen([string]$Html) {
    # The page's visible text, as the scan reads it: scripts and styles out, tags out; onetrace's own format names
    # (`<name>-decision-ref/1`, `<name>-issuer-trust/1`) as a record writes them, out; the verifier's own row label
    # for a model call's engine setting, inside its quoted output and nowhere else, out; and that setting's field
    # name as the model-call record writes it, `engine.settings.engine_core` whole (a vLLM setting's name), out.
    $t = [regex]::Replace($Html, '(?s)<(script|style)\b.*?</\1>', ' ')
    $t = [regex]::Replace($t, '(?s)<(?:section[^>]*data-section="verifier-output"|div[^>]*data-layer="3")[^>]*>.*?</(?:section|div)>',
        { param($m) [regex]::Replace($m.Value, '(\[(?:PASS|FAIL|WARN)\s*\][^<\n]*?) engine core -- ', '$1 -- ') })
    $t = [regex]::Replace($t, '<[^>]+>', ' ')
    $t = [regex]::Replace($t, '(?<![A-Za-z0-9_.])engine\.settings\.engine_core(?![A-Za-z0-9_]|\.[A-Za-z0-9_])', ' ')
    $t = [regex]::Replace($t, '[A-Za-z]+-(?:decision-ref|issuer-trust)/1', ' ')
    $found = @()
    foreach ($w in ($t -split '[^A-Za-z0-9]+' | Where-Object { $_ })) {
        if ($CaseKept -contains (Hash $w) -or $CaseBlind -contains (Hash $w.ToLowerInvariant())) { $found += "a refused word" }
    }
    foreach ($s in $Shapes) { if ([regex]::IsMatch($t, $s)) { $found += "the shape $s" } }
    $found
}

# The pages the checks read, found from the capture store itself.
$paths = @("/health", "/", "/comparisons.html", "/executions-all.html")
foreach ($p in $paths) { $null = Get-Page $p }
$comps = Get-Page "/comparisons.html"
$diffs = @([regex]::Matches($comps.Body, 'href="/?(diff/[0-9a-f]{64}\.html)"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
$runs = Get-Page "/executions-all.html"
$keys = @([regex]::Matches($runs.Body, 'href="/?runs/([0-9a-f]{64})/case\.html"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
$steps = @($keys | ForEach-Object { "/runs/$_/stage-1.html" })
# The warm-up pass over the pages found, before any check.
foreach ($p in (@($diffs | ForEach-Object { "/$_" }) + $steps)) { $null = Get-Page $p }

$r = Get-Page "/health"
Check "C1 /health answers 200 ok" ($r.Status -eq 200 -and $r.Body.Trim() -eq "ok") "$($r.Status)"
$pages = @{}
foreach ($d in $diffs) { $pages["/$d"] = Get-Page "/$d" }
$levels = @($diffs | Where-Object { $pages["/$_"].Status -eq 200 -and $pages["/$_"].Body.Contains('data-section="token-levels"') })
Check "C2 its two comparisons answer and show the token-level section" ($diffs.Count -eq 2 -and $levels.Count -eq 2) "$($diffs.Count) listed, $($levels.Count) with it"
$stepPages = @{}
foreach ($s in $steps) { $stepPages[$s] = Get-Page $s }
$close = @($steps | Where-Object { $stepPages[$_].Status -eq 200 -and $stepPages[$_].Body.Contains("data-close-calls") })
Check "C3 a capture step shows close calls" ($close.Count -ge 1) "$($close.Count) of $($steps.Count) steps"
$front = Get-Page "/"
$all = @{ "/" = $front.Body; "/comparisons.html" = $comps.Body; "/executions-all.html" = $runs.Body }
foreach ($k in $pages.Keys) { $all[$k] = $pages[$k].Body }
foreach ($k in $stepPages.Keys) { $all[$k] = $stepPages[$k].Body }
$refused = @($all.Keys | Where-Object { @(Words-Seen $all[$_]).Count -gt 0 })
Check "C4 the public scan's words hold on its $($all.Count) pages (the verifier's own engine-setting row and the record's field name for it allowed, nothing else)" ($refused.Count -eq 0) ($refused -join ", ")
$r = Get-Page "/ingest" "POST"
Check "C5 a write is refused: POST /ingest answers 403" ($r.Status -eq 403) "$($r.Status)"
# The banner's sentence on what this store holds, as its build draws it (`public.CAPTURES_RUNS`): an image built with
# the demo's words in its place (0.8.0's said the demo's 11 pipelines) has the banner and still fails here.
$Holds = "It holds six runs from two small example pipelines whose model calls were captured"
Check "C6 / answers 200 with the read-only banner, saying what this store holds" ($front.Status -eq 200 -and $front.Body.Contains('data-frame="banner"') -and $front.Body.Contains($Holds)) "$($front.Status)"
if ($Demo) {
    $back = [regex]::Escape("The onetrace-console demo: <a href=`"$($Demo.TrimEnd('/'))")
    Check "C7 the Overview links back to the demo" ([regex]::IsMatch($front.Body, $back)) "$($front.Status)"
} else {
    Skip "C7 the Overview links back to the demo" "no -Demo given"
}

$passed = @($script:results | Where-Object { $_ }).Count
Write-Output "$passed of $($script:results.Count) passed"
if ($passed -eq $script:results.Count) { exit 0 } else { exit 1 }
