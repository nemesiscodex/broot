# Copyright 2013 Daniel Narvaez
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import json
import os
import sys

from broot.root import Root


def create(config):
    root = Root(config["path"])

    root.create()

    mounted = root.mount()
    try:
        root.install_packages(config["packages"])
    finally:
        root.unmount(mounted)


def shell(config):
    if not os.path.exists(config["path"]):
        sys.exit("Create the root first")

    root = Root(config["path"])

    mounted = root.mount()
    try:
        root.run("/bin/bash")
    finally:
        root.unmount(mounted)


def run():
    if not os.geteuid() == 0:
        sys.exit("You must run the command as root")

    with open("root.json") as f:
        config = json.load(f)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("create")
    subparsers.add_parser("shell")

    args = parser.parse_args()
    if args.command == "create":
        create(config)
    if args.command == "shell":
        shell(config)
