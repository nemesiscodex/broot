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

import collections
import os
import signal
import shutil
from subprocess import check_call, check_output

from broot.builder import FedoraBuilder
from broot.builder import DebianBuilder


class Root:
    def __init__(self, config):
        self.path = os.path.abspath(config["path"])

        self._config = config
        self._mounts = self._compute_mounts()
        self._user_name = "broot"
        self._uid = os.environ["SUDO_UID"]
        self._gid = os.environ["SUDO_GID"]

        distro = config.get("distro", "debian")

        if distro == "debian":
            self._builder = DebianBuilder(self)
        elif distro == "fedora":
            self._builder = FedoraBuilder(self)
        else:
            raise ValueError("Unknown distro %s" % distro)

    def _compute_mounts(self):
        mounts = collections.OrderedDict()

        for source_path, dest_path in self._config.get("mounts", {}).items():
            full_dest_path = os.path.join(self.path, dest_path)
            mounts[os.path.abspath(source_path)] = full_dest_path

        for source_path in ["/dev", "/dev/pts", "/dev/shm", "/sys", "/proc",
                            "/tmp"]:
            mounts[source_path] = os.path.join(self.path, source_path[1:])

        return mounts

    def _get_mounted(self):
        mount_points = []

        mount_output = check_output(["mount"]).strip()
        for mounted in mount_output.split("\n"):
            mount_points.append(mounted.split(" ")[2])
        print mount_points
        return mount_points

    def activate(self):
        mounted = self._get_mounted()

        for source_path, dest_path in self._mounts.items():
            try:
                os.makedirs(dest_path)
            except OSError:
                pass

            if dest_path not in mounted:
                check_call(["mount", "--bind", source_path, dest_path])

        shutil.copyfile(os.path.join("/etc", "resolv.conf"),
                        os.path.join(self.path, "etc", "resolv.conf"))

    def _kill_processes(self):
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    chroot = os.readlink("/proc/%s/root" % pid) == self.path
                except OSError:
                    chroot = False

                if chroot:
                    try:
                        print "Killing %s" % pid
                        os.kill(int(pid), signal.SIGTERM)
                    except OSError, e:
                        print "Failed: %s" % e

    def deactivate(self):
        self._kill_processes()

        mounted = self._get_mounted()
        for mount_path in reversed(self._mounts.values()):
            if mount_path in mounted:
                check_call(["umount", mount_path])

    def install_packages(self):
        flat_packages = []
        for group in self._config["packages"].values():
            for package in group:
                if package not in flat_packages:
                    flat_packages.append(package)

        self._builder.install_packages(flat_packages)

        if "sudo" in flat_packages:
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

        self.activate()
        try:
            self.install_packages()
        finally:
            self.deactivate()

    def run(self, command, as_root=False):
        orig_home = os.environ.get("HOME", None)

        if as_root:
            chroot_command = "chroot"
            os.environ["HOME"] = "/root"
        else:
            os.environ["HOME"] = "/home/%s" % self._user_name
            chroot_command = "chroot --userspec %s:%s" % (self._uid, self._gid)

        check_call("%s %s /bin/bash -lc \"%s\"" %
                   (chroot_command, self.path, command), shell=True)

        if orig_home:
            os.environ["HOME"] = orig_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]

    def _create_user(self):
        self.run("/usr/sbin/groupadd %s --gid %s" %
                 (self._user_name, self._gid), as_root=True)

        self.run("/usr/sbin/useradd %s --uid %s --gid %s" %
                 (self._user_name, self._gid, self._uid), as_root=True)

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
