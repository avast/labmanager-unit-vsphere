$newVmName = "{{NEW_VM_NAME}}"
$networkSwitchName = "{{NETWORK_SWITCH_NAME}}"
$networkSwitchVlan = "{{NETWORK_SWITCH_VLAN}}"
Connect-VMNetworkAdapter -VMName $newVmName -SwitchName $networkSwitchName
Set-VMNetworkAdapterVlan -VMName $newVmName -Access -VlanId $networkSwitchVlan