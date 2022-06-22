from vcenter import vcenter

vm_to_uuid_dict = {
    'Win_10_Pro_64b_EN-ss-test_danek-26': '420d4985-a279-1150-2f49-21b336e0e061'

}

vc = vcenter.VCenter()
vc.connect()

for machine_name, uuid in vm_to_uuid_dict.items():

    m = vc.get_machine_by_uuid(uuid)
    is_instant_clone_frozen = m.runtime.instantCloneFrozen
    if is_instant_clone_frozen:
        print(f'[OK] Machine {machine_name} is frozen')
    else:
        print(f'[X] Machine {machine_name} is NOT frozen, freezing...')
        res = vc.freeze_vm(machine_uuid=uuid)
        print(f'    |-> Machine {machine_name} frozen: {res}')

