Get-Service |
  Where-Object { $_.Name -like 'gway-*' } |
  ForEach-Object {
    sc.exe qc $_.Name |
    Select-String '-r ' |
    ForEach-Object {
      if ($_ -match '-r\s+([^\\"\s]+)') { $matches[1] }
    }
  }
