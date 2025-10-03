$newVmName="{{VM_NAME}}"

#get host
$nodes = (Get-ClusterGroup | Where-Object {$_.GroupType -eq 'VirtualMachine'} | where-Object {$_.Name -match $newVmName}) | foreach {$_.OwnerNode.Name}
$vm = $nodes | foreach{get-vm -computername $_}|where-Object {$_.Name -match $newVmName} | select-object -first 1
$computerName = $vm.ComputerName

Start-VM -Name $newVmName -ComputerName $computerName