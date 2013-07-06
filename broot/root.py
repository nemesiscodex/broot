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

import os
import shutil
from subprocess import check_call

from broot.builder import FedoraBuilder
from broot.builder import DebianBuilder


class Root:
    def __init__(self, config):
        self.path = os.path.abspath(config["path"])

        self._config = config
        self._mounts = self._compute_mounts()
        self._user_name = "broot"

        distro = config.get("distro", "debian")

        if distro == "debian":
            self._builder = DebianBuilder(self)
        elif distro == "fedora":
            self._builder = FedoraBuilder(self)
        else:
            raise ValueError("Unknown distro %s" % distro)

    def _compute_mounts(self):
        mounts = {}

        for source_path, dest_path in self._config.get("mounts", {}).items():
            mounts[os.path.abspath(source_path)] = dest_path

        for source_path in ["/dev", "/dev/pts", "/dev/shm", "/sys", "/proc",
                            "/tmp"]:
            mounts[source_path] = os.path.join(self.path, source_path[1:])

        return mounts

    def activate(self):
        self._mounted = []

        for source_path, dest_path in self._mounts.items():
            check_call(["mount", "--bind", source_path, dest_path])
            self._mounted.append(dest_path)

        shutil.copyfile(os.path.join("/etc", "resolv.conf"),
                        os.path.join(self.path, "etc", "resolv.conf"))

    def deactivate(self):
        for mount_path in reversed(self._mounted):
            check_call(["umount", mount_path])

        del self._mounted

    def install_packages(self, packages):
        self._builder.install_packages(packages)

    def create(self):
        try:
            os.makedirs(self.path)
        except OSError:
            pass

        self._builder.create()

        self._setup_bashrc("root")

        self._create_user()
        self._setup_bashrc(os.path.join("home", self._user_name))

    def run(self, command, root=False):
        if root:
            chroot = "chroot"
        else:
            chroot = "chroot --userspec %s:%s" % (
                self._user_name, self._user_name)

        check_call("%s %s /bin/bash -lc \"%s\"" %
                   (chroot, self.path, command), shell=True)

    def _create_user(self):
        self.run(["adduser", self._user_name, "--uid", os.environ["SUDO_UID"],
                  "--gid", os.environ["SUDO_GID"]], root=True)

    def _setup_bashrc(self, home_path):
        environ = {"LANG": "C"}

        with open(os.path.join(self.path, home_path, ".bashrc"), "w") as f:
            for variable, value in environ.items():
                f.write("export %s=%s\n" % (variable, value))
