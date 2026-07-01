$ErrorActionPreference = "Stop"

$repo = "https://github.com/adamfrancis-stfc/fba-test.git"
$installDir = Join-Path "\Tools" "fba-test"
$venvDir = Join-Path $installDir ".venv"

Write-Host ""
Write-Host "=== fba-test setup ===" -ForegroundColor Cyan
Write-Host ""

# -- Check prerequisites --
foreach ($cmd in @("git", "python")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Error: '$cmd' is not installed or not on PATH." -ForegroundColor Red
        exit 1
    }
}

# -- Clone or pull --
if (Test-Path (Join-Path $installDir ".git")) {
    Write-Host "Updating existing installation..." -ForegroundColor Yellow
    git -C $installDir pull --ff-only
} else {
    Write-Host "Cloning repo..." -ForegroundColor Yellow
    git clone $repo $installDir
}

# -- Create venv if needed --
if (-not (Test-Path $venvDir)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $venvDir
}

$pip = Join-Path $venvDir "Scripts\pip.exe"

# -- Install in editable mode --
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pip install -e $installDir --quiet

# -- Add to PATH if not already there --
$binDir = Join-Path $venvDir "Scripts"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($userPath -notlike "*$binDir*") {
    Write-Host "Adding fba-test to your PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$binDir", "User")
    $env:Path = "$env:Path;$binDir"
    Write-Host "Note: restart your terminal for PATH changes to take effect in other sessions." -ForegroundColor DarkGray
}

# -- Verify --
Write-Host ""
Write-Host "Done! Run 'fba-test --help' to get started." -ForegroundColor Green
Write-Host ""
