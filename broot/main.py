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


def _get_pristine_root():
    return Root("pristine")


def _get_current_root(clone=True):
    root = Root("current")
    if clone and not root.exists():
        _get_pristine_root().clone("current")
    return root


def cmd_create(options, other_args):
    root = _get_pristine_root()
    return root.create(options.arch, options.mirror)


def cmd_run(options, other_args):
    root = _get_current_root()
    return root.run(" ".join(other_args), as_root=options.root)


def cmd_shell(options, other_args):
    root = _get_current_root()
    return root.run("/bin/bash", as_root=options.root)


def cmd_setup(options, other_args):
    root = _get_pristine_root()
    return root.setup()


def cmd_clean(options, other_args):
    root = _get_pristine_root()
    root.clean()

    root = _get_current_root()
    root.clean()

    return True


def cmd_distribute(options, other_args):
    root = _get_pristine_root()
    return root.distribute()


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

    options, other_args = parser.parse_known_args()

    cmd_function = globals()["cmd_%s" % options.command]
    if not cmd_function(options, other_args):
        sys.exit(1)
