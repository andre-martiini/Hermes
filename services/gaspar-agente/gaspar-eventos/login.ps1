# Login único do canal gaspar-eventos: troca e-mail/senha do Firebase do André por um refresh token
# e grava cifrado com DPAPI (só este usuário do Windows decifra). A senha não é gravada.
$key = if ($env:FIREBASE_WEB_API_KEY) { $env:FIREBASE_WEB_API_KEY } else { 'AIzaSyCc00Qqsa7Zgfx9NZkLoPj_gvXcuMczuxk' }
$email = Read-Host 'E-mail do Gaspar'
$sec = Read-Host 'Senha' -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$body = @{ email = $email; password = $plain; returnSecureToken = $true } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$key" -ContentType 'application/json' -Body $body
$plain = $null; $body = $null
Add-Type -AssemblyName System.Security
$enc = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($r.refreshToken), $null, 'CurrentUser')
$state = Join-Path $PSScriptRoot 'state'
New-Item -ItemType Directory -Force $state | Out-Null
[IO.File]::WriteAllBytes((Join-Path $state 'refresh.dpapi'), $enc)
Write-Host "Refresh token gravado em $state\refresh.dpapi (DPAPI, usuário atual)."
