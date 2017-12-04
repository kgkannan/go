#!/usr/bin/python
""" Test/Verify Quagga BGP State Propagation """

#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.
#

import shlex

from collections import OrderedDict

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = """
---
module: test_quagga_bgp_state_propagation
author: Platina Systems
short_description: Module to test and verify quagga bgp state propagation.
description:
    Module to test and verify bgp configurations and log the same.
options:
    switch_name:
      description:
        - Name of the switch on which tests will be performed.
      required: False
      type: str
    leaf_network_list:
      description:
        - Comma separated list of all leaf bgp networks.
      required: False
      type: str
    leaf_list:
      description:
        - List of all leaf switches.
      required: False
      type: list
      default: []
    route_present:
      description:
        - Flag to indicate if bgp route should be present in output or not.
      required: False
      type: bool
      default: True
    hash_name:
      description:
        - Name of the hash in which to store the result in redis.
      required: False
      type: str
    log_dir_path:
      description:
        - Path to log directory where logs will be stored.
      required: False
      type: str
"""

EXAMPLES = """
- name: Verify quagga bgp state propagation
  test_quagga_bgp_state_propagation:
    switch_name: "{{ inventory_hostname }}"
    hash_name: "{{ hostvars['server_emulator']['hash_name'] }}"
    log_dir_path: "{{ log_dir_path }}"
"""

RETURN = """
hash_dict:
  description: Dictionary containing key value pairs to store in hash.
  returned: always
  type: dict
"""

RESULT_STATUS = True
HASH_DICT = OrderedDict()


def run_cli(module, cli):
    """
    Method to execute the cli command on the target node(s) and
    returns the output.
    :param module: The Ansible module to fetch input parameters.
    :param cli: The complete cli string to be executed on the target node(s).
    :return: Output/Error or None depending upon the response from cli.
    """
    cli = shlex.split(cli)
    rc, out, err = module.run_command(cli)

    if out:
        return out.rstrip()
    elif err:
        return err.rstrip()
    else:
        return None


def execute_commands(module, cmd):
    """
    Method to execute given commands and return the output.
    :param module: The Ansible module to fetch input parameters.
    :param cmd: Command to execute.
    :return: Output of the commands.
    """
    global HASH_DICT

    if 'service quagga restart' in cmd:
        out = None
    else:
        out = run_cli(module, cmd)

    # Store command prefixed with exec time as key and
    # command output as value in the hash dictionary
    exec_time = run_cli(module, 'date +%Y%m%d%T')
    key = '{0} {1} {2}'.format(module.params['switch_name'], exec_time, cmd)
    HASH_DICT[key] = out

    return out


def verify_quagga_bgp_state_propagation(module):
    """
    Method to verify quagga bgp state propagation.
    :param module: The Ansible module to fetch input parameters.
    """
    global RESULT_STATUS, HASH_DICT
    failure_summary = ''
    route_present = module.params['route_present']
    leaf_list = module.params['leaf_list']
    switch_name = module.params['switch_name']
    leaf_network_list = module.params['leaf_network_list'].split(',')

    if route_present:
        # Get the current/running configurations
        execute_commands(module, "vtysh -c 'sh running-config'")

        # Restart and check Quagga status
        execute_commands(module, 'service quagga restart')
        execute_commands(module, 'service quagga status')
    else:
        leaf1 = leaf_list[0]
        key = '{} ifconfig eth-19-1 down'.format(leaf1)
        HASH_DICT[key] = None
        key = '{} ifconfig eth-3-1 down'.format(leaf1)
        HASH_DICT[key] = None

    execute_flag = True
    is_leaf = True if switch_name in leaf_list else False
    if is_leaf:
        if leaf_list.index(switch_name) == 0:
            execute_flag = False
            
    if execute_flag:
        # Get all ip routes
        cmd = "vtysh -c 'sh ip route'"
        out = execute_commands(module, cmd)

        route = 'B>* {}'.format(leaf_network_list[0])
        if route_present:
            if route not in out:
                RESULT_STATUS = False
                failure_summary += 'On Switch {} bgp route '.format(switch_name)
                failure_summary += '{} is not present '.format(route)
                failure_summary += 'in the output of command {}\n'.format(cmd)
        else:
            if route in out:
                RESULT_STATUS = False
                failure_summary += 'On Switch {} bgp route '.format(switch_name)
                failure_summary += '{} is present '.format(route)
                failure_summary += 'in the output of command {} '.format(cmd)
                failure_summary += 'even after shutting down this route\n'

    HASH_DICT['result.detail'] = failure_summary

    # Get the GOES status info
    execute_commands(module, 'goes status')


def main():
    """ This section is for arguments parsing """
    module = AnsibleModule(
        argument_spec=dict(
            switch_name=dict(required=False, type='str'),
            leaf_network_list=dict(required=False, type='str'),
            route_present=dict(required=False, type='bool', default=True),
            leaf_list=dict(required=False, type='list', default=[]),
            hash_name=dict(required=False, type='str'),
            log_dir_path=dict(required=False, type='str'),
        )
    )

    global HASH_DICT, RESULT_STATUS

    verify_quagga_bgp_state_propagation(module)

    # Calculate the entire test result
    HASH_DICT['result.status'] = 'Passed' if RESULT_STATUS else 'Failed'

    # Create a log file
    mode = 'w' if module.params['route_present'] else 'a'
    log_file_path = module.params['log_dir_path']
    log_file_path += '/{}.log'.format(module.params['hash_name'])
    log_file = open(log_file_path, mode)
    for key, value in HASH_DICT.iteritems():
        log_file.write(key)
        log_file.write('\n')
        log_file.write(str(value))
        log_file.write('\n')
        log_file.write('\n')

    log_file.close()

    # Exit the module and return the required JSON.
    module.exit_json(
        hash_dict=HASH_DICT,
        log_file_path=log_file_path
    )

if __name__ == '__main__':
    main()

