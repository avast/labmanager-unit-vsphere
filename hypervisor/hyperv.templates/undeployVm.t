#ivo - undeploy vm
$vmName = "{{VM_NAME}}"
$vmsPath = "{{STORAGE_ROOT}}\{{STORAGE_NAME}}\{{STORAGE_BASE_FOLDER}}"

#get host
$nodes = (Get-ClusterGroup | Where-Object {$_.GroupType -eq 'VirtualMachine'} | where-Object {$_.Name -match $vmName}) | foreach {$_.OwnerNode.Name}
$vm = $nodes | foreach{get-vm -computername $_}|where-Object {$_.Name -match $vmName} | select-object -first 1
$computerName = $vm.ComputerName


$specificVmPath = (join-path $vmsPath $vmName)
$numVMSInFolder = ((get-childitem $specificVmPath -R)|where {$_.Name -match "vmcx"}|measure-object).Count
if ($numVMSInFolder -gt 0){
    Stop-VM -ComputerName $computerName -Name $vmName -confirm:$false
    Remove-VM -ComputerName $computerName -Name $vmName -Force
}

Remove-Item -Recurse -Force $specificVmPath

#eof