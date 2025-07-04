#ivo - undeploy vm
$vmName = "{{VM_NAME}}"

$vmsPath = "{{STORAGE_ROOT}}\{{STORAGE_NAME}}\{{STORAGE_BASE_FOLDER}}"
$specificVmPath = (join-path $vmsPath $vmName)
$numVMSInFolder = ((get-childitem $specificVmPath -R)|where {$_.Name -match "vmcx"}|measure-object).Count
if ($numVMSInFolder -gt 0){
    Stop-VM -Name $vmName -confirm:$false
    Remove-VM -Name $vmName -Force
}

Remove-Item -Recurse -Force $specificVmPath

#eof