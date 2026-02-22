[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("bootstrap", "up", "down", "status", "test", "doctor")]
    [string]$Command = "doctor",

    [switch]$Bootstrap,
    [switch]$DependenciesOnly,
    [switch]$SkipRestore,
    [switch]$SkipIntegration,
    [string]$ComposeFile = "backend/docker-compose.yml",
    [string]$PostgresContainerName = "board_tpl_postgres",
    [string]$PostgresUser = "board_tpl_user",
    [string]$PostgresDatabase = "board_tpl",
    [string]$BackendProject = "backend/src/Board.ThirdPartyLibrary.Api/Board.ThirdPartyLibrary.Api.csproj",
    [string]$BackendSolution = "backend/Board.ThirdPartyLibrary.Backend.sln"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-CommandAvailable {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Test-SubmoduleInitialized {
    param([string]$Path)
    return Test-Path (Join-Path $Path ".git")
}

function Get-ComposeArgs {
    param([string]$Root, [string]$ComposePath)
    return @("compose", "-f", (Join-Path $Root $ComposePath))
}

function Invoke-DockerCompose {
    param(
        [string]$Root,
        [string]$ComposePath,
        [string[]]$SubArgs
    )

    $args = (Get-ComposeArgs -Root $Root -ComposePath $ComposePath) + $SubArgs
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose command failed: docker $($args -join ' ')"
    }
}

function Get-DockerContainerState {
    param([string]$ContainerName)

    $inspectOutput = & docker container inspect -f "{{.State.Status}}" $ContainerName 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    return ($inspectOutput | Out-String).Trim()
}

function Wait-ForPostgres {
    param(
        [string]$ContainerName,
        [string]$User,
        [string]$Database,
        [int]$TimeoutSeconds = 60
    )

    Write-Step "Waiting for PostgreSQL readiness (up to $TimeoutSeconds seconds)"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        & docker exec $ContainerName pg_isready -U $User -d $Database *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL is ready." -ForegroundColor Green
            return
        }

        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for PostgreSQL container '$ContainerName' to become ready."
}

function Ensure-Submodules {
    param([string]$Root)

    Assert-CommandAvailable -Name "git"

    $backendPath = Join-Path $Root "backend"
    $frontendPath = Join-Path $Root "frontend"

    if ((Test-SubmoduleInitialized -Path $backendPath) -and (Test-SubmoduleInitialized -Path $frontendPath)) {
        Write-Host "Submodules appear initialized." -ForegroundColor Green
        return
    }

    Write-Step "Initializing submodules"
    Push-Location $Root
    try {
        & git submodule update --init --recursive
        if ($LASTEXITCODE -ne 0) {
            throw "git submodule update failed."
        }
    }
    finally {
        Pop-Location
    }
}

function Restore-Backend {
    param([string]$Root, [string]$SolutionPath)

    Assert-CommandAvailable -Name "dotnet"
    $fullSolutionPath = Join-Path $Root $SolutionPath
    $backendRoot = Join-Path $Root "backend"

    Write-Step "Restoring backend solution"
    Push-Location $backendRoot
    try {
        & dotnet restore $fullSolutionPath
        if ($LASTEXITCODE -ne 0) {
            throw "dotnet restore failed."
        }
    }
    finally {
        Pop-Location
    }
}

function Start-Dependencies {
    param(
        [string]$Root,
        [string]$ComposePath,
        [string]$ContainerName,
        [string]$User,
        [string]$Database
    )

    Assert-CommandAvailable -Name "docker"

    $composeFullPath = Join-Path $Root $ComposePath
    if (-not (Test-Path $composeFullPath)) {
        throw "Compose file not found: $composeFullPath"
    }

    $existingContainerState = Get-DockerContainerState -ContainerName $ContainerName

    if ($existingContainerState -eq "running") {
        Write-Step "Reusing existing PostgreSQL container '$ContainerName' (already running)"
        Wait-ForPostgres -ContainerName $ContainerName -User $User -Database $Database
        return
    }

    if ($null -ne $existingContainerState) {
        Write-Step "Starting existing PostgreSQL container '$ContainerName' (state: $existingContainerState)"
        & docker start $ContainerName *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start existing PostgreSQL container '$ContainerName'."
        }

        Wait-ForPostgres -ContainerName $ContainerName -User $User -Database $Database
        return
    }

    Write-Step "Starting PostgreSQL via docker compose"
    Invoke-DockerCompose -Root $Root -ComposePath $ComposePath -SubArgs @("up", "-d", "postgres")

    Wait-ForPostgres -ContainerName $ContainerName -User $User -Database $Database
}

function Stop-Dependencies {
    param(
        [string]$Root,
        [string]$ComposePath,
        [string]$ContainerName
    )

    Assert-CommandAvailable -Name "docker"

    Write-Step "Stopping PostgreSQL via docker compose"
    Invoke-DockerCompose -Root $Root -ComposePath $ComposePath -SubArgs @("down")

    $remainingContainerState = Get-DockerContainerState -ContainerName $ContainerName
    if ($null -ne $remainingContainerState) {
        Write-Host "Note: container '$ContainerName' still exists (likely not created by this compose project)." -ForegroundColor Yellow
        Write-Host "Stop it manually if desired: docker stop $ContainerName" -ForegroundColor Yellow
    }
}

function Show-Status {
    param(
        [string]$Root,
        [string]$ComposePath,
        [string]$ContainerName,
        [string]$User,
        [string]$Database
    )

    Assert-CommandAvailable -Name "docker"

    Write-Step "docker compose status"
    Invoke-DockerCompose -Root $Root -ComposePath $ComposePath -SubArgs @("ps")

    $containerState = Get-DockerContainerState -ContainerName $ContainerName
    if ($null -eq $containerState) {
        Write-Host "Container '$ContainerName' was not found." -ForegroundColor Yellow
        return
    }

    Write-Step "Named PostgreSQL container status"
    Write-Host "$ContainerName : $containerState"

    Write-Step "PostgreSQL readiness"
    & docker exec $ContainerName pg_isready -U $User -d $Database
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "PostgreSQL container is not ready (or container is not running)."
    }
}

function Run-BackendApi {
    param(
        [string]$Root,
        [string]$ProjectPath,
        [bool]$DoRestore
    )

    Assert-CommandAvailable -Name "dotnet"
    $fullProjectPath = Join-Path $Root $ProjectPath
    $backendRoot = Join-Path $Root "backend"

    if (-not (Test-Path $fullProjectPath)) {
        throw "Backend project not found: $fullProjectPath"
    }

    if ($DoRestore) {
        Write-Step "Restoring backend project"
        Push-Location $backendRoot
        try {
            & dotnet restore $fullProjectPath
            if ($LASTEXITCODE -ne 0) {
                throw "dotnet restore failed."
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Step "Starting backend API (Ctrl+C to stop)"
    Push-Location $backendRoot
    try {
        & dotnet run --project $fullProjectPath
        if ($LASTEXITCODE -ne 0) {
            throw "dotnet run failed."
        }
    }
    finally {
        Pop-Location
    }
}

function Run-Tests {
    param(
        [string]$Root,
        [bool]$RunIntegration
    )

    Assert-CommandAvailable -Name "dotnet"
    $backendRoot = Join-Path $Root "backend"

    $unitProject = Join-Path $Root "backend/tests/Board.ThirdPartyLibrary.Api.Tests/Board.ThirdPartyLibrary.Api.Tests.csproj"
    $integrationProject = Join-Path $Root "backend/tests/Board.ThirdPartyLibrary.Api.IntegrationTests/Board.ThirdPartyLibrary.Api.IntegrationTests.csproj"

    Push-Location $backendRoot
    try {
        Write-Step "Running backend unit tests"
        & dotnet test $unitProject --filter "Category!=Integration"
        if ($LASTEXITCODE -ne 0) {
            throw "Unit tests failed."
        }

        if ($RunIntegration) {
            Write-Step "Running backend integration tests (Docker/Testcontainers required)"
            & dotnet test $integrationProject --filter "Category=Integration"
            if ($LASTEXITCODE -ne 0) {
                throw "Integration tests failed."
            }
        }
        else {
            Write-Host "Skipping integration tests." -ForegroundColor Yellow
        }
    }
    finally {
        Pop-Location
    }
}

function Run-Doctor {
    param(
        [string]$Root,
        [string]$ComposePath
    )

    Write-Step "Environment checks"

    foreach ($cmd in @("git", "docker", "dotnet")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            Write-Host "Found: $cmd" -ForegroundColor Green
        }
        else {
            Write-Warning "Missing command: $cmd"
        }
    }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Step "Submodule status"
        Push-Location $Root
        try {
            & git submodule status
        }
        finally {
            Pop-Location
        }
    }

    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        Write-Step ".NET SDK version"
        & dotnet --version
    }

    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Step "Docker version"
        & docker --version
        Write-Step "Docker Compose version"
        & docker compose version
    }

    $composeFullPath = Join-Path $Root $ComposePath
    if (Test-Path $composeFullPath) {
        Write-Host "Compose file found: $composeFullPath" -ForegroundColor Green
    }
    else {
        Write-Warning "Compose file missing: $composeFullPath"
    }

    Write-Host ""
    Write-Host "Suggested first-time setup:" -ForegroundColor Cyan
    Write-Host "  pwsh ./scripts/dev.ps1 bootstrap"
    Write-Host "  pwsh ./scripts/dev.ps1 up"
    Write-Host ""
    Write-Host "One-shot convenience (first run only):" -ForegroundColor Cyan
    Write-Host "  pwsh ./scripts/dev.ps1 up -Bootstrap"
}

$repoRoot = Get-RepoRoot

switch ($Command) {
    "bootstrap" {
        Ensure-Submodules -Root $repoRoot
        Restore-Backend -Root $repoRoot -SolutionPath $BackendSolution
        Write-Host "Bootstrap complete." -ForegroundColor Green
    }

    "up" {
        if ($Bootstrap) {
            Write-Host "Running bootstrap checks before startup (convenience mode)." -ForegroundColor Yellow
            Ensure-Submodules -Root $repoRoot
        }

        Start-Dependencies `
            -Root $repoRoot `
            -ComposePath $ComposeFile `
            -ContainerName $PostgresContainerName `
            -User $PostgresUser `
            -Database $PostgresDatabase

        if ($DependenciesOnly) {
            Write-Host "Dependencies are up." -ForegroundColor Green
            Write-Host "Run the API with: pwsh ./scripts/dev.ps1 up -SkipRestore" -ForegroundColor Yellow
            return
        }

        Run-BackendApi -Root $repoRoot -ProjectPath $BackendProject -DoRestore:(-not $SkipRestore)
    }

    "down" {
        Stop-Dependencies -Root $repoRoot -ComposePath $ComposeFile -ContainerName $PostgresContainerName
        Write-Host "Dependencies stopped." -ForegroundColor Green
    }

    "status" {
        Show-Status `
            -Root $repoRoot `
            -ComposePath $ComposeFile `
            -ContainerName $PostgresContainerName `
            -User $PostgresUser `
            -Database $PostgresDatabase
    }

    "test" {
        Run-Tests -Root $repoRoot -RunIntegration:(-not $SkipIntegration)
    }

    "doctor" {
        Run-Doctor -Root $repoRoot -ComposePath $ComposeFile
    }
}
