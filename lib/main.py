import configparser
import os
import re
import subprocess
import sys
from typing import Callable

import vim  # type: ignore

blocking_required = False
try:
    from ansible.cli import check_blocking_io
except SystemExit:
    blocking_required = True


class BlockingIO:
    def __init__(self):
        self.required = blocking_required
        if self.required:
            self.fd = sys.stdin.fileno()
            self._set()

    def _set(self):
        os.set_blocking(self.fd, True)

    def unset(self):
        os.set_blocking(self.fd, False)


def prepare(func: Callable):
    def wrapper():
        if func.__name__ == "encrypt":
            if is_encrypted():
                print("File is already encrypted")
                return
        elif func.__name__ == "decrypt":
            if not is_encrypted():
                print("File is already decrypted")
                return
        io_block = BlockingIO()
        func()
        io_block.unset()

    return wrapper


def get_ansibe_config_and_dir():
    ansible_cfg_file = find_ansible_config_file()
    if ansible_cfg_file:
        ansible_dir = os.path.dirname(ansible_cfg_file)
    else:
        ansible_dir = None

    return ansible_cfg_file, ansible_dir


def find_ansible_config_file() -> str | None:
    cfg_files = []
    for root, _, files in os.walk(".", topdown=False):
        for f in files:
            if f == "ansible.cfg":
                full_path = os.path.join(root, f)
                distance = len(full_path.split("/"))
                cfg_files.append({"path": full_path, "distance": distance})
    if cfg_files:
        cfg_files.sort(key=lambda v: v["distance"])
        return cfg_files[0]["path"]


def list_vault_identities(ansible_config: str) -> list[str]:
    reader = configparser.ConfigParser()
    reader.read(ansible_config)
    try:
        identity_list_line = reader["defaults"]["vault_identity_list"]
    except KeyError:
        print("vault_identity_list parameter not found in ansible.cfg")
        return []
    # Extract possible options
    #  vault_identity_list = dev@./.dev_vault , test@./.test_vault
    vault_ids = re.findall(r"(\w+)@", identity_list_line)
    return vault_ids


def run_cmd(cmd: str, dir: str):
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result


@prepare
def encrypt():
    ansible_cfg_file, ansible_dir = get_ansibe_config_and_dir()
    if not ansible_cfg_file or not ansible_dir:
        print("ansible.cfg not found. Skipping...")
        return

    vault_ids = list_vault_identities(ansible_cfg_file)
    if vault_ids:
        if len(vault_ids) > 1:
            vault_ids_str = ", ".join(vault_ids)
            vault_id = vim.eval(f'input("Enter the vault-id ({vault_ids_str})> ")')
            if vault_id not in vault_ids:
                print(f"{vault_id} is not in {vault_ids}")
                return
        else:
            vault_id = vault_ids[0]
    else:
        print("No vault-id found in ansible.cfg file. Skipping...")
        return

    current_buffer = vim.current.buffer.name
    cmd = f"ansible-vault encrypt --encrypt-vault-id {vault_id} {current_buffer}"
    result = run_cmd(cmd, ansible_dir)

    if result.returncode != 0:
        print(result.stderr)
        return


@prepare
def decrypt():
    ansible_cfg_file, ansible_dir = get_ansibe_config_and_dir()
    if not ansible_cfg_file or not ansible_dir:
        print("ansible.cfg not found. Skipping...")
        return

    current_buffer = vim.current.buffer.name

    cmd = f"ansible-vault decrypt {current_buffer}"
    result = run_cmd(cmd, ansible_dir)

    if result.returncode != 0:
        print(f'echoerr "{result.stderr}"')
        return


def is_encrypted():
    return "$ANSIBLE_VAULT" in vim.current.buffer[0]
