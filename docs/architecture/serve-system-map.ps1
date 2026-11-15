<#
.SYNOPSIS
    Serve system-map.html on a local web server and open it in the browser.

.DESCRIPTION
    A small static file server for this folder (docs/architecture), built on
    the .NET HttpListener that ships with Windows PowerShell. It needs no
    Python, no Node and no administrator rights.

    It listens on localhost only, so nothing is reachable from other machines,
    and it serves only files inside this folder.

    Stop it with Ctrl+C.

.PARAMETER Port
    Port to listen on. Default 8765. Pick another if that one is taken.

.PARAMETER NoBrowser
    Start the server without opening the browser.

.EXAMPLE
    .\docs\architecture\serve-system-map.ps1

.EXAMPLE
    .\docs\architecture\serve-system-map.ps1 -Port 9000 -NoBrowser

.NOTES
    If PowerShell refuses to run the script ("running scripts is disabled"),
    start it this way instead:

        powershell -ExecutionPolicy Bypass -File .\docs\architecture\serve-system-map.ps1
#>

param(
    [int]$Port = 8765,

    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$rootWithSeparator = $root.TrimEnd('\') + '\'
$page = "system-map.html"
$url = "http://localhost:$Port/"

if (-not (Test-Path (Join-Path $root $page))) {
    Write-Error "Cannot find $page next to this script ($root)."
    exit 1
}

$contentTypes = @{
    ".html" = "text/html; charset=utf-8"
    ".css"  = "text/css; charset=utf-8"
    ".js"   = "text/javascript; charset=utf-8"
    ".json" = "application/json; charset=utf-8"
    ".md"   = "text/plain; charset=utf-8"
    ".svg"  = "image/svg+xml"
    ".png"  = "image/png"
    ".jpg"  = "image/jpeg"
    ".jpeg" = "image/jpeg"
    ".ico"  = "image/x-icon"
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($url)

try {
    $listener.Start()
}
catch {
    Write-Error "Could not start a server on port $Port. It is probably in use; try another, e.g. -Port 9000. ($($_.Exception.Message))"
    exit 1
}

Write-Host ""
Write-Host "MemSOC system map is being served at:"
Write-Host "    $url" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop."
Write-Host ""

if (-not $NoBrowser) {
    Start-Process $url
}

try {
    while ($listener.IsListening) {

        # Wait in short slices rather than blocking, so Ctrl+C is noticed.
        $pending = $listener.GetContextAsync()

        while (-not $pending.AsyncWaitHandle.WaitOne(200)) { }

        $context = $pending.GetAwaiter().GetResult()
        $request = $context.Request
        $response = $context.Response

        try {
            $relative = [System.Uri]::UnescapeDataString($request.Url.AbsolutePath).TrimStart('/')

            if ($relative -eq "") {
                $relative = $page
            }

            $target = [System.IO.Path]::GetFullPath((Join-Path $root $relative))

            # Never serve anything outside this folder.
            $inside = $target.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)

            if ($inside -and (Test-Path $target -PathType Leaf)) {
                $bytes = [System.IO.File]::ReadAllBytes($target)
                $extension = [System.IO.Path]::GetExtension($target).ToLowerInvariant()

                if ($contentTypes.ContainsKey($extension)) {
                    $response.ContentType = $contentTypes[$extension]
                }
                else {
                    $response.ContentType = "application/octet-stream"
                }

                # The page is edited by hand; do not let the browser keep an old copy.
                $response.Headers.Add("Cache-Control", "no-store")
                $response.StatusCode = 200
            }
            else {
                $bytes = [System.Text.Encoding]::UTF8.GetBytes("404 - not found")
                $response.ContentType = "text/plain; charset=utf-8"
                $response.StatusCode = 404
            }

            $response.ContentLength64 = $bytes.Length
            $response.OutputStream.Write($bytes, 0, $bytes.Length)

            Write-Host ("{0}  {1}  {2}" -f (Get-Date -Format "HH:mm:ss"), $response.StatusCode, $request.Url.AbsolutePath)
        }
        catch {
            Write-Host "Request failed: $($_.Exception.Message)" -ForegroundColor Yellow
        }
        finally {
            $response.Close()
        }
    }
}
finally {
    $listener.Stop()
    $listener.Close()
    Write-Host "Server stopped."
}
