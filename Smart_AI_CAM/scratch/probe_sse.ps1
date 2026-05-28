# probe_sse.ps1
$ip = "127.0.0.1"
$port = 27182
$path = "/mcp"

Write-Output "Connecting to SSE MCP Server at $ip:$port..."

$client = New-Object System.Net.Sockets.TcpClient
$connect = $client.BeginConnect($ip, $port, $null, $null)
$success = $connect.AsyncWaitHandle.WaitOne(3000, $false)

if (-not $success) {
    Write-Output "Error: Connection timed out to $ip:$port"
    exit 1
}

try {
    $client.EndConnect($connect)
    Write-Output "Connected successfully! Sending HTTP GET request..."
    
    $stream = $client.GetStream()
    $writer = New-Object System.IO.StreamWriter($stream)
    $reader = New-Object System.IO.StreamReader($stream)
    
    # Send HTTP GET for SSE
    $writer.WriteLine("GET $path HTTP/1.1")
    $writer.WriteLine("Host: $ip:$port")
    $writer.WriteLine("Accept: text/event-stream")
    $writer.WriteLine("Connection: keep-alive")
    $writer.WriteLine("")
    $writer.Flush()
    
    Write-Output "Request sent. Reading response headers..."
    
    # Read headers
    $headers = @()
    while ($true) {
        $line = $reader.ReadLine()
        if ($null -eq $line -or $line -eq "") {
            break
        }
        $headers += $line
        Write-Output "Header: $line"
    }
    
    Write-Output "`nReading first few SSE events (max 5 lines)..."
    for ($i = 0; $i -lt 5; $i++) {
        $line = $reader.ReadLine()
        if ($null -eq $line) {
            Write-Output "Stream closed by server."
            break
        }
        Write-Output "SSE: $line"
    }
    
} catch {
    Write-Output "Exception: $_"
} finally {
    if ($client) {
        $client.Close()
        Write-Output "Socket connection closed."
    }
}
