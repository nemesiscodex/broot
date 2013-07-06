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
            full_dest_path = os.path.join(self.path, dest_path)
            mounts[os.path.abspath(source_path)] = full_dest_path

        for source_path in ["/dev", "/dev/pts", "/dev/shm", "/sys", "/proc",
                            "/tmp"]:
            mounts[source_path] = os.path.join(self.path, source_path[1:])

        return mounts

    def activate(self):
        self._mounted = []

        for source_path, dest_path in self._mounts.items():
            try:
                os.makedirs(dest_path)
            except OSError:
                pass

            check_call(["mount", "--bind", source_path, dest_path])
            self._mounted.append(dest_path)

        shutil.copyfile(os.path.join("/etc", "resolv.conf"),
                        os.path.join(self.path, "etc", "resolv.conf"))

    def deactivate(self):
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                if os.readlink("/proc/%s/root" % pid) == self.path:
                    os.kill(int(pid), signal.SIGTERM)

        for mount_path in reversed(self._mounted):
            check_call(["umount", mount_path])

        del self._mounted

    def install_packages(self, packages):
        self._builder.install_packages(packages)

        if "sudo" in packages:
            self._setup_sudo()

    def create(self, mirror=None):
        try:
            os.makedirs(self.path)
        except OSError:
            pass

        self._builder.create(mirror)

        self._setup_bashrc("root")

        self._create_user()
        self._setup_bashrc(os.path.join("home", self._user_name))

    def run(self, command, root=False):
        if root:
            orig_home = None
            chroot = "chroot"
        else:
            orig_home = os.environ["HOME"]
            chroot = "chroot --userspec %s:%s" % (
                self._user_name, self._user_name)

        os.environ["HOME"] = "/home/%s" % self._user_name

        check_call("%s %s /bin/bash -lc \"%s\"" %
                   (chroot, self.path, command), shell=True)

        if orig_home:
            os.environ["HOME"] = orig_home

    def _create_user(self):
        gid = os.environ["SUDO_GID"]

        self.run("/usr/sbin/addgroup %s --gid %s" % (self._user_name, gid),
                 root=True)

        self.run("/usr/sbin/adduser %s --uid %s --gid %s "
                 "--disabled-password --gecos ''" %
                 (self._user_name, os.environ["SUDO_UID"], gid), root=True)

    def _setup_bashrc(self, home_path):
        environ = {"LANG": "C"}

        with open(os.path.join(self.path, home_path, ".bashrc"), "w") as f:
            for variable, value in environ.items():
                f.write("export %s=%s\n" % (variable, value))

    def _setup_sudo(self):
        sudoers_path = os.path.join(self.path, "etc", "sudoers")

        with open(sudoers_path) as f:
            conf = f.read()

        conf = conf + "\n%s ALL=(ALL:ALL) NOPASSWD:ALL" % self._user_name

        with open(sudoers_path, "w") as f:
            f.write(conf)
