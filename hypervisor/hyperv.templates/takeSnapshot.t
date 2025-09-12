
$vmName = "{{VM_NAME}}"
$snapshotName = "{{SNAPSHOT_NAME}}"

Checkpoint-VM -vmname $vmName -snapshotname $snapshotName


#eof
