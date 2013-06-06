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

import shutil
from subprocess import check_call


class FedoraBuilder:
    def __init__(self, root):
        self._root = root

    def create(self):
        root_path = self._root.path

        release_rpm = "http://mirrors.kernel.org/fedora/development/" \
                      "19/i386/os/Packages/f/fedora-release-19-0.5.noarch.rpm"
        try:
            check_call(["rpm", "--root", root_path, "--initdb"])
            check_call(["rpm", "--root", root_path, "-i", release_rpm])
            check_call(["yum", "-y", "--installroot", root_path, "install",
                        "yum"])
        except (Exception, KeyboardInterrupt):
            shutil.rmtree(root_path)
            raise

    def install_packages(self, packages):
        self._root.run("yum -y update")
        self._root.run("yum -v -y install %s" % " ".join(packages))


class DebianBuilder:
    def __init__(self, root):
        self._root = root

    def create(self):
        root_path = self._root.path

        try:
            check_call(["debootstrap", "wheezy", root_path])
        except (Exception, KeyboardInterrupt):
            shutil.rmtree(root_path)
            raise

    def install_packages(self, packages):
        self._root.run("apt-get update")
        self._root.run("apt-get dist-upgrade")
        self._root.run("apt-get -y --no-install-recommends install %s" %
                       " ".join(packages))
