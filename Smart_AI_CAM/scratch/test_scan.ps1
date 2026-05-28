# test_scan.ps1
# Communicate with local Fusion 360 Smart_AI_CAM MCP server

$port = 9877
$ip = "127.0.0.1"

Write-Output "Connecting to Smart_AI_CAM at $ip:$port..."

$client = New-Object System.Net.Sockets.TcpClient
$connect = $client.BeginConnect($ip, $port, $null, $null)
$success = $connect.AsyncWaitHandle.WaitOne(3000, $false)

if (-not $success) {
    Write-Output "Error: Connection timed out. Please ensure Fusion 360 is running and the Smart_AI_CAM add-in is active!"
    exit 1
}

try {
    $client.EndConnect($connect)
    Write-Output "Successfully connected to Smart_AI_CAM!"
    
    $stream = $client.GetStream()
    $writer = New-Object System.IO.StreamWriter($stream)
    $reader = New-Object System.IO.StreamReader($stream)
    
    # Request scan_machining_features
    $payload = '{"action": "scan_machining_features", "params": {"material": "AL6061"}}'
    Write-Output "Sending scan request..."
    $writer.WriteLine($payload)
    $writer.Flush()
    
    Write-Output "Waiting for scan results (this might take a few seconds)..."
    $response = $reader.ReadLine()
    
    if ($response) {
        Write-Output "Scan completed successfully!"
        $json = ConvertFrom-Json $response
        if ($json.success) {
            # Print elegant summary of recognized features
            Write-Output "`n=== 3D Feature Scan Summary ==="
            Write-Output "Document Name: $($json.data.feature_catalog.setup_name)"
            Write-Output "Total Features: $($json.data.feature_catalog.feature_count)"
            
            Write-Output "`n[Counts by Category]"
            $json.data.feature_catalog.counts_by_category | Get-Member -MemberType NoteProperty | ForEach-Object {
                Write-Output "  * $($_.Name): $($json.data.feature_catalog.counts_by_category.$($_.Name))"
            }
            
            Write-Output "`n[Hole Details]"
            $json.data.holes | ForEach-Object {
                Write-Output "  * Dia: $($_.dia) mm, Depth: $($_.depth) mm, Count: $($_.count), Through: $($_.through), Direction: $($_.dir), isCBLarge: $($_.isCBLarge)"
            }
            
            Write-Output "`n[Slot Details]"
            $json.data.slots | ForEach-Object {
                Write-Output "  * Width: $($_.width_mm) mm, Length: $($_.length_mm) mm, Depth: $($_.depth_mm) mm, Count: $($_.count), Through: $($_.through)"
            }
            
            Write-Output "`n[Flat Depths (planes)]"
            $json.data.flat_depths.planes | ForEach-Object {
                Write-Output "  * Height (Z): $($_.z_height_mm) mm, Area: $($_.area_mm2) mm², Depth from Z0: $($_.depth_from_z0_mm) mm"
            }
            
            # Save raw output for inspection
            $response | Out-File -FilePath "scratch/last_scan_raw.json" -Encoding utf8
            Write-Output "`nRaw scan data saved to scratch/last_scan_raw.json"
        } else {
            Write-Output "Error in scan: $($json.error)"
        }
    } else {
        Write-Output "Error: Received empty response from server."
    }
} catch {
    Write-Output "Exception occurred: $_"
} finally {
    if ($client) { $client.Close() }
}
