<#
  edgemesh installer for Windows (PowerShell).
  Installs the `edgemesh` CLI from the current checkout (or a git URL).
  Prefers pipx, falls back to a user venv at %USERPROFILE%\.edgemesh-venv.
#>
$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:EDGEMESH_REPO) { $env:EDGEMESH_REPO } else { "https://github.com/cognis-digital/edgemesh.git" }
$Src = "."
if (-not ((Test-Path ".\pyproject.toml") -and (Select-String -Path ".\pyproject.toml" -Pattern 'name = "edgemesh"' -Quiet))) {
    $Src = "git+$RepoUrl"
}

$Py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $Py) { $Py = (Get-Command py -ErrorAction SilentlyContinue) }
if (-not $Py) { Write-Error "Python 3.10+ is required but was not found on PATH."; exit 1 }

Write-Host "edgemesh installer — using $(& $Py.Source --version) from $($Py.Source)"
Write-Host "source: $Src"

if (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "-> installing with pipx (isolated)"
    pipx install --force $Src
} else {
    $venv = Join-Path $env:USERPROFILE ".edgemesh-venv"
    Write-Host "-> pipx not found; installing into a user venv at $venv"
    & $Py.Source -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
    & "$venv\Scripts\python.exe" -m pip install $Src
    Write-Host "Installed edgemesh.exe at $venv\Scripts\edgemesh.exe"
    Write-Host "Add to PATH for this session:  `$env:Path = `"$venv\Scripts;`$env:Path`""
}

Write-Host ""
Write-Host "Installed. Next steps:"
Write-Host "  edgemesh setup     # guided setup"
Write-Host "  edgemesh menu      # interactive menu"
Write-Host "  edgemesh serve     # run the gateway"
