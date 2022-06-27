import argparse

from vcenter import vcenter

parser = argparse.ArgumentParser()
parser.add_argument('templates', type=str, metavar='vm_name', nargs='+', help='supported instant clone templates')
args = parser.parse_args()

instant_clone_templates = args.templates
print(f'Will check if following templates are instant clone frozen: {instant_clone_templates}')

vc = vcenter.VCenter()
vc.connect()


for machine_name in instant_clone_templates:

    m = vc._VCenter__search_machine_by_name(machine_name)
    is_instant_clone_frozen = m.runtime.instantCloneFrozen
    if is_instant_clone_frozen:
        print(f'[OK] Machine {machine_name} is frozen')
    else:
        print(f'[X] Machine {machine_name} is NOT frozen, freezing...')
        res = vc.freeze_vm(machine_uuid=m.config.uuid)
        print(f'    |-> Machine {machine_name} frozen: {res}')

