param([Parameter(Mandatory=$true)][string]$CertificateThumbprint,[string]$Release='desktop-dist\LightningFlow')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$releaseDirectory=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Release))
if ($releaseDirectory -notin @((Join-Path $PSScriptRoot 'desktop-dist\LightningFlow'),(Join-Path $PSScriptRoot 'desktop-next\LightningFlow'))) { throw 'Unexpected release directory' }
$certificate=Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object Thumbprint -eq $CertificateThumbprint | Select-Object -First 1
if (-not $certificate -or -not $certificate.HasPrivateKey) { throw 'A usable code-signing certificate is required. No certificate is included with the project.' }
foreach ($binary in @((Join-Path $releaseDirectory 'LightningFlow.exe'),(Join-Path $PSScriptRoot 'installers\LightningFlow-Setup.exe'))) {
    $signature=Set-AuthenticodeSignature -LiteralPath $binary -Certificate $certificate -HashAlgorithm SHA256 -TimestampServer 'http://timestamp.digicert.com'
    if ($signature.Status -ne 'Valid') { throw "Signature verification failed: $($signature.Status)" }
}
