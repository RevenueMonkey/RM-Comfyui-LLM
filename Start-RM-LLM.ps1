# Keys are read into this process only. Nothing is written to a key file or registry.
$ErrorActionPreference = 'Stop'
$rmRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
if (-not (Test-Path -LiteralPath "$rmRoot\python_embeded\python.exe") -or
    -not (Test-Path -LiteralPath "$rmRoot\ComfyUI\main.py")) {
    throw 'This launcher requires RM-LLM 0.5.0 inside a portable ComfyUI/custom_nodes directory. Otherwise use your normal ComfyUI launcher.'
}

foreach ($rmName in @('OPENROUTER_API_KEY', 'FEATHERLESS_API_KEY', 'LITHOSAI_API_KEY')) {
    $rmExisting = [System.Environment]::GetEnvironmentVariable($rmName, [System.EnvironmentVariableTarget]::Process)
    if (-not [string]::IsNullOrWhiteSpace($rmExisting)) { continue }
    $rmSecure = Read-Host "$rmName (Enter to skip)" -AsSecureString
    if ($rmSecure.Length -eq 0) { $rmSecure.Dispose(); continue }
    $rmPointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($rmSecure)
    try {
        $rmPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($rmPointer)
        [System.Environment]::SetEnvironmentVariable($rmName, $rmPlain, [System.EnvironmentVariableTarget]::Process)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($rmPointer)
        $rmSecure.Dispose()
        $rmPlain = $null
    }
}

Push-Location -LiteralPath $rmRoot
try {
    & "$rmRoot\python_embeded\python.exe" -s "$rmRoot\ComfyUI\main.py" --windows-standalone-build
}
finally {
    Pop-Location
}
