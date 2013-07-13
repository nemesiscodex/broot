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

import base64
import hashlib
import collections
import json
import os
import signal
import shutil
import tarfile
import urlgrabber
import urllib2
from subprocess import check_call, check_output

from broot.builder import FedoraBuilder
from broot.builder import DebianBuilder


class Root:
    def __init__(self):
        self._config_path = os.path.abspath("root.json")
        self._var_dir = os.path.join("/var", "lib", "broot")

        with open(self._config_path) as f:
            self._config = json.load(f)

        self.path = self._compute_path()

        self._mounts = self._compute_mounts()
        self._user_name = "broot"
        self._uid = os.environ["SUDO_UID"]
        self._gid = os.environ["SUDO_GID"]

        distro = self._config.get("distro", "debian")

        if distro == "debian":
            self._builder = DebianBuilder(self)
        elif distro == "fedora":
            self._builder = FedoraBuilder(self)
        else:
            raise ValueError("Unknown distro %s" % distro)

    def _compute_path(self):
        path_hash = hashlib.sha1()
        path_hash.update(self._config_path)
        base64_hash = base64.urlsafe_b64encode(path_hash.digest())

        return os.path.join(self._var_dir, "%s-%s" %
                            (self._config["name"], base64_hash[0:5]))

    def _compute_mounts(self):
        mounts = collections.OrderedDict()

        for source_path, dest_path in self._config.get("mounts", {}).items():
            full_dest_path = os.path.join(self.path, dest_path)
            mounts[os.path.abspath(source_path)] = full_dest_path

        system_source_paths = ["/dev",
                               "/dev/pts",
                               "/sys",
                               "/proc",
                               "/tmp",
                               "/var/run/dbus"]

        if os.path.exists("/run/shm"):
            system_source_paths.append("/run/shm")
        else:
            system_source_paths.append("/dev/shm")

        for source_path in system_source_paths:
            mounts[source_path] = os.path.join(self.path, source_path[1:])

        return mounts

    def _get_mounted(self):
        mount_points = []

        mount_output = check_output(["mount"]).strip()
        for mounted in mount_output.split("\n"):
            mount_points.append(mounted.split(" ")[2])

        return mount_points

    def activate(self):
        if not self._check_exists(True):
            return False

        mounted = self._get_mounted()

        for source_path, dest_path in self._mounts.items():
            try:
                os.makedirs(dest_path)
            except OSError:
                pass

            if dest_path not in mounted:
                try:
                    os.makedirs(dest_path)
                except OSError:
                    pass

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

    def update_packages(self):
        self._builder.update_packages()

        flat_packages = []
        for group in self._config["packages"].values():
            for package in group:
                if package not in flat_packages:
                    flat_packages.append(package)

        self._builder.install_packages(flat_packages)

        if "sudo" in flat_packages:
            self._setup_sudo()

    def _get_stamp_path(self):
        return self.path + ".stamp"

    def _check_exists(self, exists):
        if exists:
            if not os.path.exists(self.path):
                print("You must created or download the build root first.")
                return False
        else:
            if os.path.exists(self.path):
                print("The build root already exists.")
                return False

        return True

    def create(self, mirror=None):
        if not self._check_exists(False):
            return False

        try:
            os.makedirs(self.path)
        except OSError:
            pass

        self._builder.create(mirror)

        self._setup_root_bashrc()

        self._create_user()
        self._setup_user_bashrc()

        self.activate()
        try:
            self.update_packages()
            self._builder.clean_packages()
        finally:
            self.deactivate()

        with open(self._get_stamp_path(), "w") as f:
            stamp = self._config.get("stamp", "")
            f.write(stamp)
            f.close()

        return True

    def update(self):
        if not self._check_exists(True):
            return False

        try:
            with open(self._get_stamp_path()) as f:
                stamp = f.read()
        except IOError:
            stamp = ""

        if stamp == self._config.get("stamp", ""):
            self.activate()
            try:
                self.update_packages()
            finally:
                self.deactivate()
        else:
            self.clean()
            self.create()

        return True

    def clean(self):
        if not self._check_exists(True):
            return False

        self.deactivate()
        shutil.rmtree(self.path, ignore_errors=True)

        try:
            os.unlink(self._get_stamp_path())
        except OSError:
            pass

        return True

    def download(self):
        if not self._check_exists(False):
            return False

        prebuilt_url = self._config["prebuilt"]

        latest = urllib2.urlopen(prebuilt_url + "latest").read()

        tar_path = os.path.join(self._var_dir, "temp.tar.xz")

        try:
            urlgrabber.urlgrab(prebuilt_url + latest, tar_path)
            check_call(["xz", tar_path])
        except Exception, e:
            os.unlink(tar_path)
            raise e

        tar_path = os.path.join(self._var_dir, "temp.tar")

        try:
            tar = tarfile.open(tar_path)
            tar.extractall()
            tar.close()
        except Exception, e:
            os.unlink(tar_path)
            raise e

        extracted_dir = os.path.join(self._var_dir, self._config["name"])
        shutil.move(extracted_dir, self.path)

        return True

    def distribute(self):
        if not self._check_exists(True):
            return False

        name = self._config["name"]

        filename = "%s.tar" % name
        tar = tarfile.open(filename, mode="w")
        tar.add(self.path, name)
        tar.close()

        check_call(["xz", filename])

        return True

    def run(self, command, as_root=False):
        if not self._check_exists(True):
            return False

        orig_home = os.environ.get("HOME", None)

        if as_root:
            chroot_command = "chroot"
            os.environ["HOME"] = "/root"
        else:
            os.environ["HOME"] = "/home/%s" % self._user_name
            chroot_command = "chroot --userspec %s:%s" % (self._uid, self._gid)

        self.activate()
        try:
            check_call("%s %s /bin/bash -lc \"%s\"" %
                       (chroot_command, self.path, command), shell=True)
        except:
            self.deactivate()

        if orig_home:
            os.environ["HOME"] = orig_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]

        return True

    def _create_user(self):
        self.run("/usr/sbin/groupadd %s --gid %s" %
                 (self._user_name, self._gid), as_root=True)

        self.run("/usr/sbin/useradd %s --uid %s --gid %s" %
                 (self._user_name, self._gid, self._uid), as_root=True)

    def _setup_bashrc(self, home_path, extra=None):
        environ = {"LANG": "C"}

        with open(os.path.join(self.path, home_path, ".bashrc"), "w") as f:
            for variable, value in environ.items():
                f.write("export %s=%s\n" % (variable, value))
                if extra:
                    f.write(extra)

    def _setup_root_bashrc(self):
        self._setup_bashrc("root")

    def _setup_user_bashrc(self):
        shell_path = self._config.get("shell_path", None)
        if shell_path:
            extra = "cd %s" % shell_path
        else:
            extra = None

        self._setup_bashrc(os.path.join("home", self._user_name), extra)

    def _setup_sudo(self):
        sudoers_path = os.path.join(self.path, "etc", "sudoers")

        with open(sudoers_path) as f:
            conf = f.read()

        conf = conf + "\n%s ALL=(ALL:ALL) NOPASSWD:ALL" % self._user_name

        with open(sudoers_path, "w") as f:
            f.write(conf)
