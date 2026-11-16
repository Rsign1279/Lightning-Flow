"""Read-only, redacted NVIDIA TDR event count for local GPU benchmarks."""
from datetime import datetime,timezone
import json
import os
import subprocess


def utc_now():return datetime.now(timezone.utc).isoformat()


def tdr_count(since):
    timestamp=datetime.fromisoformat(since).astimezone(timezone.utc).isoformat()
    script="""
$events=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='nvlddmkm';StartTime=[datetime]::Parse('%s')} -ErrorAction SilentlyContinue -ErrorVariable eventErrors)
if ($eventErrors | Where-Object { $_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*' }) { throw 'NVIDIA event log could not be read' }
$count=@($events | Where-Object { ($_.Properties.Value -join ' ') -match 'TDR' }).Count
@{nvidia_TDR_events=$count} | ConvertTo-Json -Compress
exit 0
""" % timestamp
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,
        text=True,timeout=15,creationflags=0x08000000 if os.name=='nt' else 0)
    if result.returncode:raise RuntimeError('Windows NVIDIA event log query failed')
    return json.loads(result.stdout)['nvidia_TDR_events']
