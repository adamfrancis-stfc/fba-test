$ErrorActionPreference = "Stop"

$repo = "https://github.com/Addy010/fba-test.git"
$installDir = Join-Path "Tools" "fba-test"

Write-Host ""
Write-Host "=== fba-test setup ===" -ForegroundColor Cyan
Write-Host ""

foreach ($cmd in @("git", "python")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Error: '$cmd' is not installed or not on PATH." -ForegroundColor Red
        exit 1
    }
}

if (Test-Path (Join-Path $installDir ".git")) {
    Write-Host "Updating existing installation..." -ForegroundColor Yellow
    git -C $installDir pull --ff-only
} else {
    Write-Host "Cloning repo..." -ForegroundColor Yellow
    git clone $repo $installDir
}

Write-Host "Installing..." -ForegroundColor Yellow
pip install -e $installDir --quiet --break-system-packages

Write-Host ""
Write-Host "Done! Run 'fba-test --help' to get started." -ForegroundColor Green
Write-Host ""