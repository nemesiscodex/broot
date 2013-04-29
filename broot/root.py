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
import signal
import shutil
from subprocess import check_call


class Root:
    def __init__(self, path):
        self._path = os.path.abspath(path)

    def mount(self):
        mounted = []

        for source_path in ["/dev", "/dev/pts", "/dev/shm", "/sys", "/proc",
                            "/tmp"]:
            dest_path = os.path.join(self._path, source_path[1:])
            check_call(["mount", "--bind", source_path, dest_path])
            mounted.append(dest_path)

        return mounted

    def unmount(self, mounted):
        for mount_path in reversed(mounted):
            check_call(["umount", mount_path])

    def install_packages(self, packages):
        self.run("apt-get update")
        self.run("apt-get dist-upgrade")
        self.run("apt-get -y install %s" % " ".join(packages))

    def create(self):
        try:
            os.makedirs(self._path)
        except OSError:
            pass

        try:
            check_call(["debootstrap", "wheezy", self._path])
        except (Exception, KeyboardInterrupt):
            shutil.rmtree(self._path)
            raise

        self._setup_bashrc()

    def run(self, command):
        check_call("chroot %s /bin/bash -lc \"%s\"" %
                   (self._path, command), shell=True)

    def _setup_bashrc(self):
        environ = {"LANG": "C"}

        with open(os.path.join(self._path, "root", ".bashrc"), "w") as f:
            for variable, value in environ.items():
                f.write("export %s=%s\n" % (variable, value))
