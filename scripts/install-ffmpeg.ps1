param([string]$InstallRoot = 'C:\MeetingTranscriber')

$ErrorActionPreference = 'Stop'
$resolvedRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($resolvedRoot -ne 'C:\MeetingTranscriber') { throw "Unexpected install root: $resolvedRoot" }

$toolsRoot = Join-Path $resolvedRoot 'tools'
$target = Join-Path $toolsRoot 'ffmpeg'
$staging = Join-Path $toolsRoot 'ffmpeg-staging'
$archive = Join-Path $toolsRoot 'ffmpeg-release-essentials.zip'
$hashFile = "$archive.sha256"
New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null

Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $archive
Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256' -OutFile $hashFile
$expected = ((Get-Content -Raw $hashFile).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "FFmpeg SHA-256 mismatch" }

if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $staging -Force
$bin = Get-ChildItem -LiteralPath $staging -Directory | ForEach-Object { Join-Path $_.FullName 'bin' } | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'ffprobe.exe') } | Select-Object -First 1
if (-not $bin) { throw 'ffprobe.exe not found in verified archive' }

if (Test-Path -LiteralPath $target) { throw "Target already exists: $target" }
New-Item -ItemType Directory -Path $target | Out-Null
Copy-Item -LiteralPath (Join-Path $bin 'ffmpeg.exe') -Destination $target
Copy-Item -LiteralPath (Join-Path $bin 'ffprobe.exe') -Destination $target
if (Test-Path -LiteralPath (Join-Path $bin 'ffplay.exe')) { Copy-Item -LiteralPath (Join-Path $bin 'ffplay.exe') -Destination $target }

& (Join-Path $target 'ffmpeg.exe') -version | Select-Object -First 1
& (Join-Path $target 'ffprobe.exe') -version | Select-Object -First 1
Remove-Item -LiteralPath $staging -Recurse -Force
Remove-Item -LiteralPath $archive -Force
Remove-Item -LiteralPath $hashFile -Force
