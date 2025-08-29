$vmName = "{{VM_NAME}}"
$snapshotName = "{{SNAPSHOT_NAME}}"

#Connect-VMNetworkAdapter -VMName $newVmName -SwitchName $networkSwitchName
#Set-VMNetworkAdapterVlan -VMName $newVmName -Access -VlanId $networkSwitchVlan