<#
 Copyright (c) 2026 Maxim Pavlov
 SPDX-License-Identifier: GPL-3.0-or-later
#>

# Install KiPng into the current user's KiCad 10.0 plugin directory.
$ErrorActionPreference = 'Stop'

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
foreach ($name in @('requirements.txt', 'icon-light.png', 'icon-dark.png', 'kipng-logo.svg', 'kipng-logo.ico', 'preview.py', 'plugin.json')) {
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
    if ($installedId -ne $expectedId) {
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
