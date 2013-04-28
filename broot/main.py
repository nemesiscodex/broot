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
import os
import sys

from broot.root import Root


def create(args):
    root = Root(args.root_dir)

    root.create()

    mounted = root.mount()
    try:
        root.install_packages(["build-essential"])
    finally:
        root.unmount(mounted)


def shell(args):
    if not os.path.exists(args.root_dir):
        sys.exit("The specified root dir does not exists")

    root = Root(args.root_dir)

    mounted = root.mount()
    try:
        root.run("/bin/bash")
    finally:
        root.unmount(mounted)


def run():
    if not os.geteuid() == 0:
        sys.exit("You must run the command as root")

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    build_parser = subparsers.add_parser("create")
    build_parser.add_argument("root_dir")

    shell_parser = subparsers.add_parser("shell")
    shell_parser.add_argument("root_dir")

    args = parser.parse_args()
    if args.command == "create":
        create(args)
    if args.command == "shell":
        shell(args)
