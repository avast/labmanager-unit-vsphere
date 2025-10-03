$newVmName = "{{NEW_VM_NAME}}"
$networkSwitchName = "{{NETWORK_SWITCH_NAME}}"
$networkSwitchVlan = "{{NETWORK_SWITCH_VLAN}}"

#get host
$nodes = (Get-ClusterGroup | Where-Object {$_.GroupType -eq 'VirtualMachine'} | where-Object {$_.Name -match $newVmName}) | foreach {$_.OwnerNode.Name}
$vm = $nodes | foreach{get-vm -computername $_}|where-Object {$_.Name -match $newVmName} | select-object -first 1
$computerName = $vm.ComputerName


Connect-VMNetworkAdapter -VMName $newVmName -SwitchName $networkSwitchName -ComputerName $computerName
Set-VMNetworkAdapterVlan -VMName $newVmName -Access -VlanId $networkSwitchVlan -ComputerName $computerName