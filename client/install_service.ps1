param(
    [string]$ExecutablePath = ".\Client.exe"
)

# The installer script delegates service registration to the client itself so
# the service name and arguments stay in one place: the application config.
if (-not (Test-Path $ExecutablePath)) {
    throw "Client executable not found: $ExecutablePath"
}

& $ExecutablePath --install-service
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Windows service"
}

Write-Host "Service installed successfully."
