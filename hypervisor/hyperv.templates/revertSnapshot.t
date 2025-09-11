
$vmName = "{{VM_NAME}}"
$snapshotName = "{{SNAPSHOT_NAME}}"

Restore-VMSnapshot -VMName $vmName -Name $snapshotName -Confirm:$false

#eof
