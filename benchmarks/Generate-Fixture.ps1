$ErrorActionPreference = 'Stop'
$speechText = 'Please send the updated project report to John on Friday at three. We need to review CUDA performance and confirm the next meeting date.'
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'reference.txt'), $speechText, (New-Object System.Text.UTF8Encoding($false)))
$speechFormat = New-Object -ComObject SAPI.SpAudioFormat
$speechFormat.Type = 18 # PCM16, mono, 16000 Hz
$speechVoice = New-Object -ComObject SAPI.SpVoice
$speechStream = New-Object -ComObject SAPI.SpFileStream
$speechStream.Format = $speechFormat
$speechStream.Open((Join-Path $PSScriptRoot 'synthetic.wav'), 3, $false)
try {
    $speechVoice.AudioOutputStream = $speechStream
    $speechVoice.Speak($speechText) | Out-Null
} finally {
    $speechStream.Close()
}
Write-Host 'Created synthetic.wav locally using the current Windows SAPI voice. No network service is used.'
