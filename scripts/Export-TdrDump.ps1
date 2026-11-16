[CmdletBinding()]
param(
    [string]$DumpName = 'WATCHDOG-20261115-2254.dmp',
    [string]$FixturePath = ''
)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$workRoot=[IO.Path]::GetFullPath((Join-Path $repoRoot '.work'))
$privateRoot=Join-Path $workRoot 'kernel-diagnostics'
New-Item -ItemType Directory -Path $privateRoot -Force | Out-Null
$testMode=-not [string]::IsNullOrWhiteSpace($FixturePath)
$statusPath=Join-Path $privateRoot $(if ($testMode) {'status-test.json'} else {'status.json'})
$status=@{state='running';test_mode=$testMode;copied_dump=$null;sha256=$null;error=$null}
$temporary=$null
function Save-Status {
    $status.updated_utc=[DateTime]::UtcNow.ToString('o')
    $text=$status | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText($statusPath,$text,(New-Object Text.UTF8Encoding($false)))
}
function Get-Sha256([string]$Path) {
    $algorithm=[Security.Cryptography.SHA256]::Create()
    $stream=[IO.File]::OpenRead($Path)
    try {return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','').ToLower()}
    finally {$stream.Dispose();$algorithm.Dispose()}
}
try {
    Save-Status
    if ($DumpName -notmatch '^WATCHDOG-\d{8}-\d{4}\.dmp$') { throw 'Choose an exact WATCHDOG dump filename, without directories.' }
    if ($testMode) {
        $source=[IO.Path]::GetFullPath($FixturePath)
        if (-not $source.StartsWith($workRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Test fixtures must be inside this checkout''s ignored .work directory.'
        }
    } else {
        $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
        $principal=New-Object Security.Principal.WindowsPrincipal($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'Windows requires administrator approval to read this kernel report. Run Export-TdrDump.vbs and approve UAC.'
        }
        $source=Join-Path $env:windir ('LiveKernelReports\WATCHDOG\'+$DumpName)
    }
    $item=Get-Item -LiteralPath $source
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'The dump must be a regular file.' }
    $stamp=[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fffffff')
    $destination=Join-Path $privateRoot ($DumpName.Substring(0,$DumpName.Length-4)+'-export-'+$stamp+'.dmp')
    $temporary=$destination+'.part'
    # Copy file data only. Source ownership/permissions are never changed.
    $inputStream=[IO.File]::Open($source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        $outputStream=[IO.File]::Open($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$inputStream.CopyTo($outputStream,1048576);$outputStream.Flush($true)} finally {$outputStream.Dispose()}
    } finally {$inputStream.Dispose()}
    $sourceHash=Get-Sha256 $source
    $copyHash=Get-Sha256 $temporary
    if ($sourceHash -ne $copyHash) { throw 'The source changed or the copied report failed verification. No completed export was created.' }
    Move-Item -LiteralPath $temporary -Destination $destination
    $temporary=$null
    $status.state='complete';$status.copied_dump=$destination;$status.sha256=$copyHash
    $status.bytes=(Get-Item -LiteralPath $destination).Length
    Save-Status
    Write-Output ('Verified private export: '+$destination)
} catch {
    $status.state='error';$status.error=$_.Exception.Message
    Save-Status
    if ($temporary -and [IO.File]::Exists($temporary)) {[IO.File]::Delete($temporary)}
    Write-Error $status.error
    exit 1
}
