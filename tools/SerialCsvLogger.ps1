param(
  [string]$Port,
  [int]$BaudRate = 115200,
  [string]$OutputDir,
  [switch]$ListPorts
)

$ErrorActionPreference = "Stop"

if (-not $OutputDir) {
  $OutputDir = Join-Path (Split-Path -Parent $PSScriptRoot) "data\serial"
}

$Columns = @(
  "received_at_iso",
  "segment_id",
  "node_id",
  "timestamp",
  "mode",
  "collection_label",
  "inference_class",
  "cigarette_detected",
  "inference_score",
  "model_version",
  "voc_raw",
  "co_raw",
  "voc_mv",
  "co_mv",
  "pm1_0",
  "pm2_5",
  "pm10",
  "temperature",
  "humidity",
  "pms_valid",
  "button_mode_data_collection",
  "button_cooking_fume",
  "button_vehicle_exhaust",
  "button_cigarette_smoke",
  "button_led_cigarette",
  "raw_json"
)

function Show-Ports {
  $ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
  if ($ports.Count -eq 0) {
    Write-Host "# no serial ports found"
    return
  }

  Write-Host "# serial ports:"
  foreach ($candidate in $ports) {
    Write-Host "#   $candidate"
  }
}

function Get-Value {
  param(
    [object]$Object,
    [string]$Name
  )

  if ($null -eq $Object) {
    return $null
  }

  $property = $Object.PSObject.Properties[$Name]
  if ($null -eq $property) {
    return $null
  }

  return $property.Value
}

function ConvertTo-CsvCell {
  param([object]$Value)

  if ($null -eq $Value) {
    return ""
  }

  if ($Value -is [bool]) {
    $text = $Value.ToString().ToLowerInvariant()
  } else {
    $text = [string]$Value
  }

  if ($text -match '[,"\r\n]') {
    return '"' + $text.Replace('"', '""') + '"'
  }

  return $text
}

function New-SafeName {
  param([string]$Value)

  if ([string]::IsNullOrWhiteSpace($Value)) {
    return "unknown"
  }

  return ($Value -replace '[^A-Za-z0-9_.-]', '_')
}

function Get-SegmentInfo {
  param([object]$Reading)

  $mode = [string](Get-Value $Reading "mode")
  if ([string]::IsNullOrWhiteSpace($mode)) {
    $mode = "unknown_mode"
  }

  $nodeId = [string](Get-Value $Reading "node_id")
  if ([string]::IsNullOrWhiteSpace($nodeId)) {
    $nodeId = "unknown_node"
  }

  if ($mode -eq "data_collection") {
    $label = [string](Get-Value $Reading "collection_label")
    if ([string]::IsNullOrWhiteSpace($label)) {
      $label = "unlabeled"
    }
  } else {
    $label = "inference"
  }

  $key = "$nodeId|$mode|$label"
  return [pscustomobject]@{
    Key = $key
    NodeId = $nodeId
    Mode = $mode
    Label = $label
  }
}

function New-Segment {
  param([object]$Info)

  $startedAt = Get-Date
  $segmentId = $startedAt.ToString("yyyyMMdd_HHmmss")
  $node = New-SafeName $Info.NodeId
  $mode = New-SafeName $Info.Mode
  $label = New-SafeName $Info.Label
  $fileName = "${segmentId}_${node}_${mode}_${label}.csv"
  $path = Join-Path $OutputDir $fileName

  New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
  Set-Content -Path $path -Value ($Columns -join ",") -Encoding UTF8

  Write-Host "# opened segment: $path"

  return [pscustomobject]@{
    Key = $Info.Key
    Id = $segmentId
    Path = $path
    RowCount = 0
    StartedAt = $startedAt
  }
}

function Close-Segment {
  param([object]$Segment)

  if ($null -eq $Segment) {
    return
  }

  Write-Host "# closed segment: $($Segment.Path) rows=$($Segment.RowCount)"
}

function Convert-ReadingToCsvLine {
  param(
    [object]$Reading,
    [object]$Segment,
    [string]$RawJson
  )

  $buttons = Get-Value $Reading "buttons"
  $values = [ordered]@{
    received_at_iso = (Get-Date).ToString("o")
    segment_id = $Segment.Id
    node_id = Get-Value $Reading "node_id"
    timestamp = Get-Value $Reading "timestamp"
    mode = Get-Value $Reading "mode"
    collection_label = Get-Value $Reading "collection_label"
    inference_class = Get-Value $Reading "inference_class"
    cigarette_detected = Get-Value $Reading "cigarette_detected"
    inference_score = Get-Value $Reading "inference_score"
    model_version = Get-Value $Reading "model_version"
    voc_raw = Get-Value $Reading "voc_raw"
    co_raw = Get-Value $Reading "co_raw"
    voc_mv = Get-Value $Reading "voc_mv"
    co_mv = Get-Value $Reading "co_mv"
    pm1_0 = Get-Value $Reading "pm1_0"
    pm2_5 = Get-Value $Reading "pm2_5"
    pm10 = Get-Value $Reading "pm10"
    temperature = Get-Value $Reading "temperature"
    humidity = Get-Value $Reading "humidity"
    pms_valid = Get-Value $Reading "pms_valid"
    button_mode_data_collection = Get-Value $buttons "mode_data_collection"
    button_cooking_fume = Get-Value $buttons "cooking_fume"
    button_vehicle_exhaust = Get-Value $buttons "vehicle_exhaust"
    button_cigarette_smoke = Get-Value $buttons "cigarette_smoke"
    button_led_cigarette = Get-Value $buttons "led_cigarette"
    raw_json = $RawJson
  }

  return ($Columns | ForEach-Object { ConvertTo-CsvCell $values[$_] }) -join ","
}

if ($ListPorts) {
  Show-Ports
  if (-not $Port) {
    exit 0
  }
}

if ([string]::IsNullOrWhiteSpace($Port)) {
  Show-Ports
  throw "Pass -Port COMx. Example: powershell -ExecutionPolicy Bypass -File .\tools\SerialCsvLogger.ps1 -Port COM5"
}

$serial = [System.IO.Ports.SerialPort]::new(
  $Port,
  $BaudRate,
  [System.IO.Ports.Parity]::None,
  8,
  [System.IO.Ports.StopBits]::One
)
$serial.ReadTimeout = 1000
$serial.NewLine = "`n"

$currentSegment = $null

try {
  $serial.Open()
  Write-Host "# listening on $Port at $BaudRate baud"
  Write-Host "# output dir: $OutputDir"
  Write-Host "# close Arduino Serial Monitor before running this logger"
  Write-Host "# press Ctrl+C to stop"

  while ($true) {
    try {
      $line = $serial.ReadLine().Trim()
    } catch [System.TimeoutException] {
      continue
    }

    if ([string]::IsNullOrWhiteSpace($line)) {
      continue
    }

    if (-not $line.StartsWith("{")) {
      Write-Host $line
      continue
    }

    try {
      $reading = $line | ConvertFrom-Json
    } catch {
      Write-Host "# skipped invalid JSON: $line"
      continue
    }

    $info = Get-SegmentInfo $reading

    if ($null -eq $currentSegment -or $currentSegment.Key -ne $info.Key) {
      Close-Segment $currentSegment
      $currentSegment = New-Segment $info
    }

    $csvLine = Convert-ReadingToCsvLine $reading $currentSegment $line
    Add-Content -Path $currentSegment.Path -Value $csvLine -Encoding UTF8
    $currentSegment.RowCount++

    Write-Host ("# logged {0} {1}/{2} rows={3}" -f
      (Get-Value $reading "node_id"),
      (Get-Value $reading "mode"),
      $info.Label,
      $currentSegment.RowCount)
  }
} catch {
  Write-Host "# logger stopped: $($_.Exception.Message)"
  throw
} finally {
  Close-Segment $currentSegment
  if ($serial.IsOpen) {
    $serial.Close()
  }
}
