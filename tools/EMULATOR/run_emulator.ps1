# 지정한 이미지(cue)를 DuckStation으로 실행한다. 기본값은 config/local.json의 원본.
param([string]$Image)
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$cfg = Get-Content (Join-Path $root 'config/local.json') -Raw -Encoding utf8 | ConvertFrom-Json
if (-not $Image) { $Image = Join-Path $root ([IO.Path]::ChangeExtension($cfg.source_bin, '.cue')) }
& (Join-Path $root $cfg.emulator) -- $Image
