$vmName="{{VM_NAME}}"

#get host
$nodes = (Get-ClusterGroup | Where-Object {$_.GroupType -eq 'VirtualMachine'} | where-Object {$_.Name -match $vmName}) | foreach {$_.OwnerNode.Name}
$vm = $nodes | foreach{get-vm -computername $_}|where-Object {$_.Name -match $vmName} | select-object -first 1
$computerName = $vm.ComputerName



$vm = Get-VM -Name $vmName -ComputerName $computerName
$vm_state = $vm.state

$mac = (Get-VMNetworkAdapter $vmName -ComputerName $computerName)[0].MacAddress
$ips = (Get-VMNetworkAdapter $vmName -ComputerName $computerName)[0].IPAddresses
$ips_string = $ips -join ','
echo "OUT::MAC=${mac}"
echo "OUT::IPS=${ips_string}"
echo "OUT::STATE=${vm_state}"
$vmid = $vm.id.Guid
echo "OUT::VMUUID=${vmid}"
$hostfqdn = [System.Net.Dns]::GetHostEntry($vm.ComputerName).HostName
echo "OUT::HOSTFQDN=${hostfqdn}"


#eof
