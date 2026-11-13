<#
.SYNOPSIS
Start the Linux server in Docker Desktop, or stop/show logs for its container.
.EXAMPLE
.\Start-Server.ps1 -GameData 'C:\Games\Jedi Knight' -StateDir 'C:\JK Server State'
.EXAMPLE
.\Start-Server.ps1 -Command stop
#>
[CmdletBinding()]
param(
    [string]$GameData = $env:JK_GAME_DATA,
    [string]$StateDir = $env:JK_STATE_DIR,
    [ValidateSet('start', 'stop', 'logs')]
    [string]$Command = 'start'
)

$ErrorActionPreference = 'Stop'

try {
    if ($Command -eq 'start') {
        if ([string]::IsNullOrWhiteSpace($GameData)) {
            throw "Supply -GameData with your installed game-data folder (containing resource and episode)."
        }
        $gameItem = Get-Item -LiteralPath $GameData -ErrorAction Stop
        if (-not $gameItem.PSIsContainer -or $gameItem.PSProvider.Name -ne 'FileSystem') {
            throw 'The selected game-data path must be an existing filesystem directory.'
        }
        $env:JK_GAME_DATA = (Resolve-Path -LiteralPath $GameData).ProviderPath
        if ([string]::IsNullOrWhiteSpace($StateDir)) {
            $userDirectory = [Environment]::GetFolderPath('UserProfile')
            if ([string]::IsNullOrWhiteSpace($userDirectory)) {
                throw 'Supply -StateDir: a user home directory could not be determined.'
            }
            $StateDir = Join-Path $userDirectory '.jk-cross-server'
        }
        $statePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($StateDir)
        [void][IO.Directory]::CreateDirectory($statePath)
        $env:JK_STATE_DIR = (Resolve-Path -LiteralPath $statePath).ProviderPath
        $probe = Join-Path $env:JK_STATE_DIR ('.write-test-' + [Guid]::NewGuid().ToString('N'))
        try {
            $stream = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
            $stream.Dispose()
        }
        finally {
            if ([IO.File]::Exists($probe)) { [IO.File]::Delete($probe) }
        }
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker was not found. Install and start Docker Desktop with Linux containers, then retry. This launcher does not install it.'
    }
    $dockerOS = & docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0 -or ($dockerOS -join '').Trim() -ne 'linux') {
        throw 'Docker must be running with Linux containers. Start Docker Desktop and select Linux containers, then retry.'
    }
    if ($Command -eq 'stop') {
        & docker stop jk-cross-server
    }
    elseif ($Command -eq 'logs') {
        & docker logs --tail 200 --follow jk-cross-server
    }
    else {
        & docker compose version --short | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required (docker compose). Update Docker Desktop, then retry.' }
        $compose = Join-Path $PSScriptRoot 'packaging/compose.yaml'
        if (-not (Test-Path -LiteralPath $compose -PathType Leaf)) {
            throw 'packaging/compose.yaml is missing. Extract the complete release ZIP before starting.'
        }
        & docker compose --project-name jk-cross-server --project-directory $PSScriptRoot -f $compose up --build -d
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'Container started. Open http://127.0.0.1:8765 and select a map to start the game.'
            Write-Host "Persistent state: $env:JK_STATE_DIR"
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE)." }
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
