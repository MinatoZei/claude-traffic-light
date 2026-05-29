param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("running", "needs_confirmation", "finished", "idle")]
    [string]$Status
)

$ErrorActionPreference = "SilentlyContinue"

$dir = Join-Path $env:USERPROFILE ".claude\traffic_status"
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# Find parent claude.exe PID by walking up the process tree
$pid_file = Join-Path $dir "__claude_pid__"

$claudePid = $null
if (Test-Path $pid_file) {
    $cached = Get-Content $pid_file -ErrorAction SilentlyContinue
    $proc = Get-Process -Id $cached -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -eq "claude") {
        $claudePid = $cached
    }
}

if (-not $claudePid) {
    $myPid = [System.Diagnostics.Process]::GetCurrentProcess().Id
    $currentPid = $myPid
    while ($currentPid -and $currentPid -ne 0) {
        $proc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $currentPid" -Property ProcessId,ParentProcessId,Name -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        if ($proc.Name -eq "claude.exe") {
            $claudePid = $currentPid
            break
        }
        $currentPid = $proc.ParentProcessId
    }

    if ($claudePid) {
        $claudePid | Out-File $pid_file -Encoding utf8 -NoNewline
    } else {
        # Fallback: use a random session ID
        $claudePid = "s_$(Get-Random -Minimum 100000 -Maximum 999999)"
    }
}

# Write status
$data = @{
    status = $Status
    ts     = [DateTimeOffset]::Now.ToUnixTimeSeconds()
}
$json = $data | ConvertTo-Json -Compress
$outFile = Join-Path $dir "$claudePid.json"
[System.IO.File]::WriteAllText($outFile, $json, [System.Text.UTF8Encoding]::new($false))
