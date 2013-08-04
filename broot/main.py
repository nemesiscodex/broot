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


def main():
    if not os.geteuid() == 0:
        sys.exit("You must run the command as root")

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    shell_parser = subparsers.add_parser("shell")
    shell_parser.add_argument("--root", action="store_true")

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--arch")
    create_parser.add_argument("--mirror")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--mirror")
    run_parser.add_argument("--root", action="store_true")

    subparsers.add_parser("setup")
    subparsers.add_parser("distribute")
    subparsers.add_parser("clean")

    root = Root()

    options, other_args = parser.parse_known_args()
    if options.command == "create":
        result = root.create(options.arch, options.mirror)
    elif options.command == "run":
        args = " ".join(other_args)
        result = root.run(args, as_root=options.root)
    elif options.command == "shell":
        result = root.run("/bin/bash", as_root=options.root)
    elif options.command == "setup":
        result = root.setup()
    elif options.command == "clean":
        root.clean()
        result = True
    elif options.command == "distribute":
        result = root.distribute()

    if not result:
        sys.exit(1)
