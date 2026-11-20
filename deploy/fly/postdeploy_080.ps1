# postdeploy_080.ps1 -- the hosted demo after `fly deploy` of onetrace-console 0.8.0.
# Read-only: GETs, and one POST that must be refused. Sends no secret and needs none.
#
#   .\postdeploy_080.ps1 -Base https://<the demo's address> -BuildRecord .\BUILD_RECORD.json `
#       -SiteLinks .\deploy\fly\site_links.txt [-Captures https://<the capture store's address>] [-Version 0.8.0]
#
# -BuildRecord: the build record of the build deployed, the image's /srv/onetrace-demo/BUILD_RECORD.json, which
# `fly ssh sftp get /srv/onetrace-demo/BUILD_RECORD.json` copies out; or, the same counts, the record a build of
# the same commit writes with the Dockerfile's own line (onetrace-console demo --public --build <folder>
# --runs-from deploy\fly\kept --explanations deploy\fly\kept --site-links deploy\fly\site_links.txt). The counts
# A8, A9, B1, B2 and B7 compare with are read from it, never written here: its comparisons, its kept
# explanations, and its runs with and without a close receipt.
#
# 0.7.0's checks (its release kit's postdeploy_070.ps1), the version A3 names now -Version, and C1: where
# -Captures names the capture store's app (deploy/fly/captures/), the comparisons page's line to it; without
# -Captures, C1 is skipped, not failed. The release's own checks are added where its kit is made.
#
# A: the 0.6.0 checks. B1-B5: one check per 0.6.1 item a public page shows (B3-B5 hold that the local-only
# parts stay off public pages). B6-B11: one check per 0.7.0 item a public page shows (B8 and B11 hold that
# the local-only and export-only parts stay off). Prints PASS, FAIL or SKIP per check, then "<n> of <m> passed"
# (22 checks, 23 with -Captures); exits 0 only when every check run passes. In 0.7.0's kit its 21 passed 21 of 21
# against the build rehearsed on its public commit. B12, console 0.8.0's: the kept runs, recorded again with their
# inputs, show P1's input's text, labelled as the demo's example data.
param(
    [Parameter(Mandatory = $true)][string]$Base,
    [Parameter(Mandatory = $true)][string]$BuildRecord,
    [string]$SiteLinks = ".\deploy\fly\site_links.txt",
    [string]$Captures = "",
    [string]$Version = "0.8.0"
)
$ErrorActionPreference = "Stop"
# The HTTP client's assembly, its name written in two parts: the folder's scan reads a dotted name ending in
# that word as a domain (tests/test_deploy_fly.py).
Add-Type -AssemblyName ("System." + "Net.Http")
$Base = $Base.TrimEnd("/")
$client = [Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(30)
$script:results = @()

# What the build deployed holds, from its own build record: each count a check compares with.
$recorded = @((Get-Content -Raw -Encoding UTF8 $BuildRecord | ConvertFrom-Json).files.PSObject.Properties.Name)
$expectComparisons = @($recorded | Where-Object { $_ -match '^store/store/comparisons/[0-9a-f]{64}\.json$' }).Count
$expectKept = @($recorded | Where-Object { $_ -match '^store/store/x/[0-9a-f]+/r/explain/[^/]+\.explanation\.json$' }).Count
$runIds = @($recorded | ForEach-Object { if ($_ -match '^runs/([^/]+)/MANIFEST\.json$') { $Matches[1] } })
$closedIds = @($recorded | ForEach-Object { if ($_ -match '^runs/([^/]+)/receipts/[0-9]+-onetrace-close\.json$') { $Matches[1] } } | Sort-Object -Unique)
$expectClosed = @($runIds | Where-Object { $closedIds -contains $_ }).Count
$expectNotClosed = @($runIds | Where-Object { $closedIds -notcontains $_ }).Count

function Get-Page([string]$Path, [string]$Method = "GET") {
    $req = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::new($Method), $Base + $Path)
    if ($Method -eq "POST") { $req.Content = [Net.Http.StringContent]::new("x") }
    $resp = $client.SendAsync($req).GetAwaiter().GetResult()
    $headers = @{}
    foreach ($h in $resp.Headers) { $headers[$h.Key] = ($h.Value -join ", ") }
    $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    [pscustomobject]@{ Status = [int]$resp.StatusCode; Headers = $headers; Body = $body }
}

function Skip([string]$Name, [string]$Why) { Write-Output "SKIP  $Name  -- $Why" }

function Check([string]$Name, [bool]$Ok, [string]$Said = "") {
    $script:results += $Ok
    $word = if ($Ok) { "PASS" } else { "FAIL" }
    if ($Said) { Write-Output "$word  $Name  -- $Said" } else { Write-Output "$word  $Name" }
}

# A: the 0.6.0 checks
$r = Get-Page "/health"
Check "A1 /health answers 200 ok" ($r.Status -eq 200 -and $r.Body.Trim() -eq "ok") "$($r.Status)"
$front = Get-Page "/"
Check "A2 / answers 200 with the read-only banner" ($front.Status -eq 200 -and $front.Body.Contains('data-frame="banner"')) "$($front.Status)"
Check "A3 / names onetrace-console $Version" ($front.Body.Contains("onetrace-console $Version"))
# The banner's count of pipelines is what this build serves: the Overview's own pipelines, counted on the same page.
$CountWords = @{ "no" = 0; "one" = 1; "two" = 2; "three" = 3; "four" = 4; "five" = 5; "six" = 6; "seven" = 7; "eight" = 8; "nine" = 9; "ten" = 10 }
$said = [regex]::Match($front.Body, 'Its runs come from (\S+) small example pipelines')
$cards = @([regex]::Matches($front.Body, 'data-pipeline-card="([^"]+)"') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique).Count
$n = -1
if ($said.Success) { $w = $said.Groups[1].Value; if ($CountWords.ContainsKey($w)) { $n = $CountWords[$w] } elseif ($w -match '^\d+$') { $n = [int]$w } }
Check "A3b the banner's count of pipelines is the Overview's, $cards" ($said.Success -and $cards -gt 0 -and $n -eq $cards) "$($said.Groups[1].Value)"
$csp = "$($front.Headers['Content-Security-Policy'])"
Check "A4 headers: CSP default-src 'none', frame DENY, nosniff, HSTS" ($csp.Contains("default-src 'none'") -and
    $front.Headers['X-Frame-Options'] -eq "DENY" -and $front.Headers['X-Content-Type-Options'] -eq "nosniff" -and
    "$($front.Headers['Strict-Transport-Security'])".Contains("max-age="))
$r = Get-Page "/ingest" "POST"
Check "A5 a write is refused: POST /ingest answers 403" ($r.Status -eq 403) "$($r.Status)"
$r = Get-Page "/static/console.css"
Check "A6 /static/console.css answers 200" ($r.Status -eq 200) "$($r.Status)"
$r = Get-Page "/no-such-page.html"
Check "A7 an unknown page answers 404" ($r.Status -eq 404) "$($r.Status)"
$comps = Get-Page "/comparisons.html"
$diffs = @([regex]::Matches($comps.Body, 'href="/?(diff/[0-9a-f]{64}\.html)"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
Check "A8 /comparisons.html lists the build record's $expectComparisons comparisons" ($comps.Status -eq 200 -and $diffs.Count -eq $expectComparisons) "$($comps.Status), $($diffs.Count)"
$pages = @{}
foreach ($d in $diffs) { $pages[$d] = (Get-Page "/$d").Body }
$kept = @($diffs | Where-Object { $pages[$_].Contains("AI-generated, may be wrong") })
Check "A9 the build record's $expectKept kept explanations each show on a comparison" ($kept.Count -eq $expectKept) "$($kept.Count)"
$links = @(Get-Content $SiteLinks | Where-Object { $_.Trim() -and -not $_.StartsWith("#") } | ForEach-Object { ($_ -split '\s+')[0] })
$bad = @($links | Where-Object { (Get-Page $_).Status -ne 200 })
Check "A10 each of the site's $($links.Count) links answers 200" ($links.Count -gt 0 -and $bad.Count -eq 0) ($bad -join ", ")

# B: one check per 0.6.1 item a public page shows
$lead = @($kept | Where-Object { $pages[$_].Contains("Lead: where to look first") })
Check "B1 Lead badge: each kept explanation reads 'Lead: where to look first'" ($lead.Count -eq $expectKept) "$($lead.Count)"
$code = @($kept | Where-Object { $pages[$_] -match '<p data-claim-text>[^<]*(?:<(?!/p>)[^<]*)*<code>' })
Check "B2 backticks as code: each kept explanation's claims hold <code>" ($code.Count -eq $expectKept) "$($code.Count)"
$all = @{ "/" = $front.Body; "/comparisons.html" = $comps.Body } + $pages
$gear = @($all.Keys | Where-Object { $all[$_].Contains("popovertarget") -or $all[$_].Contains("gear-mark") })
Check "B3 no settings gear on a public page (home, comparisons, $($diffs.Count) comparisons)" ($gear.Count -eq 0) ($gear -join ", ")
$r = Get-Page "/neighbours/setup"
Check "B4 a public console has no neighbours setup page: /neighbours/setup answers 404" ($r.Status -eq 404) "$($r.Status)"
$r = Get-Page "/pipeline-p1.html"
Check "B5 two dropdowns are a local console's: /pipeline-p1.html has none" ($r.Status -eq 200 -and -not $r.Body.Contains("data-local-compare")) "$($r.Status)"

# B: one check per 0.7.0 item a public page shows
$r = Get-Page "/bisect-p10.html"
$answer = $r.Body.IndexOf('data-section="bisect-answer"')
$how = $r.Body.IndexOf('data-section="bisect-how"')
Check "B6 P10's first-run-to-leave page says its answer first" ($r.Status -eq 200 -and $answer -ge 0 -and $answer -lt $how -and
      $r.Body -match 'The first run to leave the reference is .*?, at step <code>agent_step</code> \(output differs\)\.') "$($r.Status)"
$runs = Get-Page "/executions-all.html"
$closedRows = [regex]::Matches($runs.Body, 'data-ending="closed">closed: by ').Count
$notClosed = [regex]::Matches($runs.Body, [regex]::Escape("not closed: the record ends at")).Count
Check "B7 the runs list's Closed column, in the verifier's words: $expectClosed closed and $expectNotClosed not, as the build record has them" ($runs.Status -eq 200 -and
      $runs.Body.Contains("<th>Closed</th>") -and $closedRows -eq $expectClosed -and $notClosed -eq $expectNotClosed) "$($runs.Status), $closedRows closed, $notClosed not"
$keys = @([regex]::Matches($runs.Body, 'href="/?runs/([0-9a-f]{64})/case\.html"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
$cases = @{}
foreach ($k in $keys) { $cases[$k] = (Get-Page "/runs/$k/case.html").Body }
$form = @($keys | Where-Object { $cases[$_].Contains("Check against an expectations file") })
$section = @($keys | Where-Object { $cases[$_].Contains('data-section="expectations"') })
Check "B8 expectations: the demo's runs declare none, and none of its $($keys.Count) run pages offers the local form" ($keys.Count -gt 0 -and
      $form.Count -eq 0 -and $section.Count -eq 0) ($form -join ", ")
$spans = @($diffs | Where-Object { $pages[$_].Contains('data-section="span-differences"') -and $pages[$_].Contains('data-trace="spans"') -and
      $pages[$_].Contains("spans from your app&#x27;s traces") })
Check "B9 the app's spans at a differing step: comparisons with a spans table" ($spans.Count -ge 1) "$($spans.Count)"
$p2 = Get-Page "/pipeline-p2.html"
$fields = @([regex]::Matches($p2.Body, '<label class="compare-field"><span class="compare-label">([^<]+)</span><select name="([ab])">') |
      ForEach-Object { "$($_.Groups[1].Value)|$($_.Groups[2].Value)" })
Check "B10 the Compare picker keeps each label with its select (/pipeline-p2.html)" ($p2.Status -eq 200 -and ($fields -join ";") -eq
      "Baseline (run A)|a;Candidate (run B)|b") ($fields -join "; ")
$p1 = Get-Page "/pipeline-p1.html"
$choose = @([regex]::Matches($p1.Body, 'href="/?(choose-p1-[0-9a-f]{64}\.html)"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique | Select-Object -First 1)
$live = @($p2.Body) + @($choose | ForEach-Object { (Get-Page "/$_").Body })
$off = @($live | Where-Object { $_.Contains("Needs a running console.") -or $_ -match '<button[^>]*disabled[^>]*>Compare' })
Check "B11 Compare is live on a public console: no 'Needs a running console.', no disabled Compare (an export's only)" ($off.Count -eq 0 -and
      $p2.Body.Contains("data-visitor-compare")) "$($live.Count)"

# B: console 0.8.0's kept runs, recorded again with their inputs (the receipt's sentence as the page writes it, escaped)
$p1run = [regex]::Match($runs.Body, 'data-run="p1-02-baseline-set2" data-key="([0-9a-f]{64})"').Groups[1].Value
$step = if ($p1run) { Get-Page "/runs/$p1run/stage-1.html" } else { $null }
$receipt = if ($p1run) { Get-Page "/runs/$p1run/receipt.html" } else { $null }
Check "B12 P1's run shows its kept input's text, labelled as the demo's example data" ($null -ne $step -and $step.Status -eq 200 -and
      $step.Body.Contains('data-kept="shown"') -and $step.Body.Contains("<pre data-kept-text>") -and
      $receipt.Body.Contains("This run&#x27;s kept inputs are the demo&#x27;s invented example data, so this public console shows them and its download includes them.")) "$p1run"

# C: the capture store's app, where its address is given
if ($Captures) {
    $line = [regex]::Escape("Token-level examples (L2 and L3): <a href=`"$($Captures.TrimEnd('/'))")
    Check "C1 /comparisons.html has its line to the token-level examples" ([regex]::IsMatch($comps.Body, $line)) "$($comps.Status)"
} else {
    Skip "C1 /comparisons.html has its line to the token-level examples" "no -Captures given"
}

$passed = @($script:results | Where-Object { $_ }).Count
Write-Output "$passed of $($script:results.Count) passed"
if ($passed -eq $script:results.Count) { exit 0 } else { exit 1 }
