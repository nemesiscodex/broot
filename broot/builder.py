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
import textwrap
from subprocess import check_call


class FedoraBuilder:
    def __init__(self, root):
        self._root = root

    def _setup_yum(self):
        yum_etc_path = os.path.join(self._root.path, "etc", "yum")
        os.makedirs(yum_etc_path)

        yum_conf = """
                      [main]
                      cachedir=/var/cache/yum
                      keepcache=1
                      debuglevel=2
                      logfile=/var/log/yum.log
                      exactarch=1
                      obsoletes=1
                   """

        yum_conf_path = os.path.join(self._root.path, "etc", "yum", "yum.conf")

        with open(yum_conf_path, "w") as f:
            f.write(textwrap.dedent(yum_conf))

        base_url = "ftp://mirrors.kernel.org/fedora/releases/19/Fedora/" \
                   "x86_64/os"

        repo_config = """
            [fedora]
            name=Fedora 19 - x86_64
            failovermethod=priority
            baseurl=%s
            enabled=1
            gpgcheck=0
            ignore_os=1""" % base_url

        repos_d_path = os.path.join(self._root.path, "etc", "yum.repos.d")

        with open(os.path.join(repos_d_path, "fedora.repo"), "w") as f:
            f.write(textwrap.dedent(repo_config))

        for repo_name in "fedora-updates", "fedora-updates-testing":
            os.unlink(os.path.join(repos_d_path, "%s.repo" % repo_name))

    def create(self, mirror=None):
        root_path = self._root.path

        release_rpm = "ftp://mirrors.kernel.org/fedora/releases/19/Fedora/" \
                      "x86_64/os/Packages/f/fedora-release-19-2.noarch.rpm"
        try:
            check_call(["rpm", "--root", root_path, "--initdb"])
            check_call(["rpm", "--root", root_path, "--ignoreos", "-i",
                        release_rpm])

            self._setup_yum()
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
