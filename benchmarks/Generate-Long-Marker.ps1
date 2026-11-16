$ErrorActionPreference='Stop'
$markerRoot=Join-Path $PSScriptRoot '..\.work\long-recording'
New-Item -ItemType Directory -Path $markerRoot -Force | Out-Null
$markerText='This is the final sentence. The recovery marker is silver mountain.'
[System.IO.File]::WriteAllText((Join-Path $markerRoot 'final-marker.txt'),$markerText)
$markerFormat=New-Object -ComObject SAPI.SpAudioFormat
$markerFormat.Type=18 # 16 kHz mono PCM16
$markerVoice=New-Object -ComObject SAPI.SpVoice
$markerStream=New-Object -ComObject SAPI.SpFileStream
$markerStream.Format=$markerFormat
$markerStream.Open((Join-Path $markerRoot 'final-marker.wav'),3,$false)
try {
    $markerVoice.AudioOutputStream=$markerStream
    $markerVoice.Speak($markerText) | Out-Null
} finally { $markerStream.Close() }
Write-Output 'Generated synthetic final marker; no audio played or recorded.'
