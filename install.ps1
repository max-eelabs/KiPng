<#
 Copyright (c) 2026 Maxim Pavlov
 SPDX-License-Identifier: GPL-3.0-or-later
#>

[CmdletBinding()]
param(
    [switch]$Local,
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

function New-PcmArchive($files, [string]$outputPath) {
    $metadata = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'metadata.json') -Raw -Encoding UTF8
    $versions = ($metadata | ConvertFrom-Json).versions
    if (@($versions).Count -ne 1 -or $versions[0].version -notmatch '^[0-9]{1,4}(\.[0-9]{1,4}(\.[0-9]{1,6})?)?\z') {
        throw 'PCM archive metadata must declare one valid package version.'
    }
    $version = $versions[0].version
    $projectVersion = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'VERSION') -Raw).Trim()
    $expectedVersion = if ($versions[0].status -eq 'development') { "$version-SNAPSHOT" } else { $version }
    if ($projectVersion -cne $expectedVersion) {
        throw "VERSION must be $expectedVersion to match metadata.json."
    }
    if (-not $outputPath) {
        $outputPath = Join-Path $PSScriptRoot "dist\KiPng-$projectVersion.zip"
    }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($outputPath)
    if ([IO.Path]::GetExtension($destination) -ne '.zip') {
        throw 'The PCM output path must end in .zip.'
    }

    # Build beside the destination so an interrupted build leaves any previous ZIP intact.
    $directory = Split-Path -Parent $destination
    [void][IO.Directory]::CreateDirectory($directory)
    $temporary = Join-Path $directory ([guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $archive = [IO.Compression.ZipFile]::Open($temporary, [IO.Compression.ZipArchiveMode]::Create)
        try {
            $writer = [IO.StreamWriter]::new($archive.CreateEntry('metadata.json').Open())
            try {
                $writer.Write($metadata)
            } finally {
                $writer.Dispose()
            }
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive, (Join-Path $PSScriptRoot 'resources\icon.png'), 'resources/icon.png')
            foreach ($relative in $files.Keys) {
                $entry = 'plugins/' + $relative.Replace('\', '/')
                [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive, $files[$relative], $entry)
            }
        } finally {
            $archive.Dispose()
        }

        if ([IO.File]::Exists($destination)) {
            [IO.File]::Replace($temporary, $destination, [NullString]::Value)
        } else {
            [IO.File]::Move($temporary, $destination)
        }
    } finally {
        [IO.File]::Delete($temporary)
    }

    Write-Output "Built KiPng PCM package: $destination"
    Write-Output 'In the KiCad Project Manager, open Plugin and Content Manager > Install from File and select the ZIP.'
}

function Get-ContentHash([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    try {
        $hash = [Security.Cryptography.SHA256]::Create()
        try {
            return [Convert]::ToBase64String($hash.ComputeHash($stream))
        } finally {
            $hash.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

$plugin = Join-Path $PSScriptRoot 'plugin'
$source = Join-Path $PSScriptRoot 'src'
$package = Join-Path $source 'kipng'
if (-not (Test-Path -LiteralPath (Join-Path $package '__init__.py') -PathType Leaf)) {
    throw 'Missing the KiPng runtime package.'
}

# Assemble KiCad's install layout from the distribution files and the source package.
$files = [ordered]@{}
$files['LICENSE'] = Join-Path $PSScriptRoot 'LICENSE'
$files['VERSION'] = Join-Path $PSScriptRoot 'VERSION'
$files['VERSION'] = Join-Path $PSScriptRoot 'VERSION'
foreach ($name in @('requirements.txt', 'icon-light.png', 'icon-dark.png', 'kipng-logo.svg', 'kipng-logo.ico', 'preview.py', 'render.py', 'plugin.json')) {
    $file = Join-Path $plugin $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing plugin file: $name"
    }
    $files[$name] = $file
}
foreach ($file in Get-ChildItem -LiteralPath $package -Recurse -File) {
    if ($file.Extension -in '.py', '.qml') {
        $files[$file.FullName.Substring($source.Length + 1)] = $file.FullName
    }
}

if (-not $Local) {
    New-PcmArchive $files $OutputPath
    return
}

# Derive parent paths for nested modules so updates reject unsafe destinations.
$directories = [Collections.Generic.HashSet[string]]::new()
foreach ($relative in $files.Keys) {
    $parent = Split-Path -Parent $relative
    while ($parent) {
        [void]$directories.Add($parent)
        $parent = Split-Path -Parent $parent
    }
}

$documents = if ($env:KICAD_DOCUMENTS_HOME) {
    $env:KICAD_DOCUMENTS_HOME
} else {
    [Environment]::GetFolderPath('MyDocuments')
}
if (-not $documents) {
    throw 'Could not locate the KiCad documents directory.'
}

$destination = Join-Path $documents 'KiCad\10.0\plugins\kipng'
$expectedId = (Get-Content -LiteralPath $files['plugin.json'] -Raw -Encoding UTF8 |
    ConvertFrom-Json).identifier
$updating = Test-Path -LiteralPath $destination
if ($updating) {
    $existing = Get-Item -LiteralPath $destination -Force
    if (-not $existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "The install path is not a regular directory: $destination"
    }
    $manifest = Join-Path $destination 'plugin.json'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw "The install folder exists without a KiPng manifest: $destination"
    }
    $installedId = (Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json).identifier
    if ($installedId -ne $expectedId -and $installedId -ne 'org.kipng.preview') {
        throw "A different plugin occupies the install folder: $destination"
    }
}

foreach ($relative in ($directories | Sort-Object Length)) {
    $target = Join-Path $destination $relative
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "The runtime package path is not a regular directory: $target"
        }
    }
}

foreach ($file in $files.Keys) {
    $target = Join-Path $destination $file
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "The install target is not a regular file: $target"
        }
    }
}

if ($updating) {
    $installPath = $destination
} else {
    $versionRoot = Split-Path -Parent (Split-Path -Parent $destination)
    $installPath = Join-Path $versionRoot ("kipng-install-" + [guid]::NewGuid().ToString('N'))
}

try {
    [void][IO.Directory]::CreateDirectory($installPath)
    foreach ($file in $files.Keys) {
        $original = $files[$file]
        $target = Join-Path $installPath $file
        $hash = Get-ContentHash $original
        if ([IO.File]::Exists($target) -and (Get-ContentHash $target) -ceq $hash) {
            continue
        }
        [void][IO.Directory]::CreateDirectory((Split-Path -Parent $target))
        [IO.File]::Copy($original, $target, $true)
        if ((Get-ContentHash $target) -cne $hash) {
            throw "Installed file did not match the source: $target"
        }
    }
    if (-not $updating) {
        [void][IO.Directory]::CreateDirectory((Split-Path -Parent $destination))
        [IO.Directory]::Move($installPath, $destination)
    }
} finally {
    if (-not $updating -and [IO.Directory]::Exists($installPath)) {
        foreach ($file in $files.Keys) {
            [IO.File]::Delete((Join-Path $installPath $file))
        }
        foreach ($relative in ($directories | Sort-Object Length -Descending)) {
            $directory = Join-Path $installPath $relative
            if ([IO.Directory]::Exists($directory)) {
                [IO.Directory]::Delete($directory)
            }
        }
        [IO.Directory]::Delete($installPath)
    }
}

Write-Output "Installed KiPng in $destination"
