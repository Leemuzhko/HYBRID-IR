# Run the receipt-based uninstaller outside its own Python DLL directory.
# Only this newly allocated temporary directory is recursively removed.
$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$stage = Join-Path $temporaryRoot ('HYBRIDIR-uninstall-' + [guid]::NewGuid().ToString('N'))
$stage = [IO.Path]::GetFullPath($stage)
if ((Split-Path -Parent $stage).TrimEnd('\') -ne $temporaryRoot.TrimEnd('\')) { throw 'Unsafe temporary path' }
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $manifest = Get-Content -LiteralPath (Join-Path $appRoot 'PUBLICATION_MANIFEST.json') -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 'hybridir-publication/1') { throw 'Invalid manifest' }
    foreach ($entry in $manifest.files) {
        $name = [string]$entry.path
        if ($name -notin @('uninstaller.py', 'installation_guard.py') -and
            ($name -notlike 'runtime/*' -or $name -like 'runtime/Lib/site-packages/*')) { continue }
        if ($name.Contains('..') -or $name.Contains(':') -or $name.Contains('\') -or $name.StartsWith('/')) { throw 'Unsafe runtime path' }
        $source = [IO.Path]::GetFullPath((Join-Path $appRoot $name))
        if (-not $source.StartsWith($appRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escaped installation' }
        $partPath = $source
        while ($partPath) {
            # AppData and other hidden ancestors still require the same link check.
            $part = Get-Item -LiteralPath $partPath -Force
            if ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime path' }
            $partPath = Split-Path -Parent $partPath
        }
        $hasher = [Security.Cryptography.SHA256]::Create()
        $stream = [IO.File]::OpenRead($source)
        try { $hash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
        if ($hash -ne $entry.sha256) { throw "Modified uninstall runtime: $name" }
        $target = Join-Path $stage $name
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target
    }
    Push-Location $stage
    try {
        & (Join-Path $stage 'runtime/python.exe') -B -X utf8 (Join-Path $stage 'uninstaller.py') --root $appRoot
        if ($LASTEXITCODE -ne 0) { throw 'Uninstaller failed' }
    } finally { Pop-Location }
} catch {
    Write-Host $_ -ForegroundColor Red
    throw
} finally {
    # The path was allocated above and validated as a direct child of TEMP.
    Remove-Item -LiteralPath $stage -Recurse -Force
}
