$templName = "{{TEMPLATE_NAME}}"
$newVmName = "{{NEW_VM_NAME}}"

$networkSwitchName = "{{NETWORK_SWITCH_NAME}}"
$networkSwitchVlan = {{NETWORK_SWITCH_VLAN}}

$vmTemplatesPath = "{{STORAGE_ROOT}}\{{TEMPLATES_STORAGE_NAME}}\{{TEMPLATES_FOLDER_NAME}}"
$vmPathBase = "{{STORAGE_ROOT}}\{{STORAGE_NAME}}\{{STORAGE_BASE_FOLDER}}"
$vmConfig = (get-childitem (join-path $vmTemplatesPath $templName)|where{$_.Name -match ".*vm$"}).FullName
$vmDisk = (get-childitem (join-path $vmTemplatesPath $templName)|where{$_.Name -match ".*vhd*"}).FullName

$matchCPU = get-content $vmConfig |select-string "CPU="
if ($matchCPU.Line -eq $null)
{
    echo "Error getting CPU"
    pause
    exit 10
}
$matchRAM = get-content $vmConfig |select-string "RAM="
if ($matchRAM.Line -eq $null)
{
    echo "Error getting RAM"
    pause
    exit 10
}
$memoryStartupBytes = [int]($matchRAM.Line -replace ".*=", "")*1024*1024
$cpuCount = [int]($matchCPU.Line -replace ".*=", "")


$newVMPath = Join-Path $vmPathBase $newVmName
if(Test-path $newVMPath)
{
	echo "VM to be deployed exists"
    pause
	exit 15
}

$newVhdPath = Join-Path $newVMPath "disk.vhd"


function Get-LeastLoadedHost {
    Get-ClusterNode |
        Where-Object { $_.State -eq 'Up' } |
        Sort-Object {
			$vms = Get-VM -ComputerName $_.Name
			$count_r = ($vms|?{$_.state -in "Starting","Running", "Stopping", "Resetting", "Migrating"}|measure-object).count
			$count_s = ($vms|?{$_.state -in "Off","Saved", "Paused", "Suspended"}|measure-object).count
			return ($count_r + ($count_s/3))
        } |
        Select-Object -First 1
}
#$targetHost = (Get-ClusterNode)[0]
$targetHost = Get-LeastLoadedHost

New-Item -ItemType Directory -Path $newVMPath -Force | Out-Null

Write-Host "[$newVmName] creating vhd..."
Measure-command {New-VHD -ParentPath "$vmDisk" -Path $newVhdPath -Differencing}
#Measure-command {Copy-Item -Path $snapshotFile -Destination $newVhdPath -Force}


Write-Host "[$newVmName] creating VM..."
New-VM -Name $newVmName `
	   -ComputerName $targetHost.Name `
	   -MemoryStartupBytes $memoryStartupBytes `
	   -Generation 1 `
	   -VHDPath $newVhdPath `
	   -Path $newVMPath | Out-Null

Write-Host "[$newVmName] setting count of CPU ..."
Set-VM -Name $newVmName -ComputerName $targetHost.Name -ProcessorCount $cpuCount
Set-VM -Name $newVmName -ComputerName $targetHost.Name -CheckpointType Standard

#generate random MAC
$mac = "00-15-5D" + ("{0:X2}" -f (Get-Random -Minimum 0 -Maximum 256)) + ("{0:X2}" -f (Get-Random -Minimum 0 -Maximum 256)) + ("{0:X2}" -f (Get-Random -Minimum 0 -Maximum 256))

Write-Host "[$newVmName] setting static MAC ..."
Set-VMNetworkAdapter -VMName $newVmName -ComputerName $targetHost.Name -StaticMacAddress $mac

Add-ClusterVirtualMachineRole -VirtualMachine $newVmName

#eof