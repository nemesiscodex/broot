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
from subprocess import check_call, check_output


class FedoraBuilder:
    def __init__(self, root):
        self._root = root

    def _setup_yum(self, mirror):
        for repo_name in ["fedora", "fedora-updates",
                          "fedora-updates-testing"]:
            repo_path = os.path.join(self._root.path, "etc", "yum.repos.d",
                                     "%s.repo" % repo_name)

            with open(repo_path) as f:
                conf = ""
                for line in f.readlines():
                    if line.startswith("#baseurl"):
                        line = line[1:]
                        line.replace("http://download.fedoraproject.org"
                                     "/pub/fedora/linux", mirror)

                    if line.startswith("mirrorlist"):
                        line = "#" + line

                    if line.startswith("gpgkey"):
                        line = "gpgkey=http://fedoraproject.org/" \
                               "static/FB4B18E6.txt"

                    conf = conf + line

            with open(repo_path, "w") as f:
                f.write(conf)

    def _setup_rpm(self):
        db_path = check_output(["rpm", "-E", "%_dbpath"]).strip()

        rpmmacros_path = os.path.join(self._root.path, "root", ".rpmmacros")
        with open(rpmmacros_path, "w") as f:
            f.write("%%_dbpath %%(%s)" % db_path)
            f.close()

    def create(self, mirror=None):
        root_path = self._root.path

        if mirror is None:
            mirror = "ftp://mirrors.kernel.org/fedora"

        release_rpm = "%s/releases/19/Fedora/x86_64/os/Packages/f/" \
                      "fedora-release-19-2.noarch.rpm" % mirror
        try:
            check_call(["rpm", "--root", root_path, "--initdb"])
            check_call(["rpm", "--root", root_path, "-i", release_rpm])

            self._setup_rpm()
            self._setup_yum(mirror)

            check_call(["yum", "-y", "--installroot", root_path, "install",
                        "yum"])
        except (Exception, KeyboardInterrupt):
            shutil.rmtree(root_path)
            raise

    def install_packages(self, packages):
        self._root.run("yum -y update", root=True)
        self._root.run("yum -v -y install %s" % " ".join(packages), root=True)


class DebianBuilder:
    def __init__(self, root):
        self._root = root

    def create(self, mirror=None):
        root_path = self._root.path

        try:
            args = ["debootstrap", "jessie", root_path]
            if mirror is not None:
                args.append(mirror)

            check_call(args)
        except (Exception, KeyboardInterrupt):
            shutil.rmtree(root_path)
            raise

    def install_packages(self, packages):
        self._root.run("apt-get update", root=True)
        self._root.run("apt-get dist-upgrade", root=True)
        self._root.run("apt-get -y --no-install-recommends install %s" %
                       " ".join(packages), root=True)
