
$vmName = "{{VM_NAME}}"
$snapshotName = "{{SNAPSHOT_NAME}}"

Remove-VMSnapshot -VMName $vmName -Name $snapshotName

#eof
