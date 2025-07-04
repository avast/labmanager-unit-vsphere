$vmName="{{VM_NAME}}"

$vm = Get-VM -Name $vmName
$vm_state = $vm.state

$mac = (Get-VMNetworkAdapter $vmName)[0].MacAddress
$ips = (Get-VMNetworkAdapter $vmName)[0].IPAddresses
$ips_string = $ips -join ','
echo "OUT::MAC=${mac}"
echo "OUT::IPS=${ips_string}"
echo "OUT::STATE=${vm_state}"

#eof
