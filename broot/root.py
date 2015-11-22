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
import urllib2
from subprocess import check_call, call, check_output

import wget

from broot.builder import FedoraBuilder
from broot.builder import DebianBuilder


class Root:
    STATE_NONE = "none"
    STATE_READY = "ready"
    STATE_INVALID = "invalid"

    def __init__(self):
        self._config_path = os.path.abspath("root.json")
        self._var_dir = os.path.join("/var", "lib", "broot")
        self._use_run_shm = os.path.exists("/run/shm")
        self._hash_len = 5

        with open(self._config_path) as f:
            self._config = json.load(f)

        self.path = self._compute_path()

        self._mounts = self._compute_mounts()
        self._user_name = "broot"
        self._uid = int(os.environ["SUDO_UID"])
        self._gid = int(os.environ["SUDO_GID"])

        distro = self._config.get("distro", "debian")

        if distro == "debian":
            self._builder = DebianBuilder(self)
        elif distro in ["fedora", "fedora-20", "fedora-23"]:
            self._builder = FedoraBuilder(self, distro)
        else:
            raise ValueError("Unknown distro %s" % distro)

    def _compute_path(self):
        path_hash = hashlib.sha1()
        path_hash.update(self._config_path)

        base64_hash = base64.b64encode(path_hash.digest())
        base64_hash = base64_hash.replace("+", "0")
        base64_hash = base64_hash.replace("/", "0")

        return os.path.join(self._var_dir, "%s-%s" %
                            (self._config["name"],
                             base64_hash[0:self._hash_len]))

    def _get_user_mounts(self):
        return self._config.get("user_mounts", {})

    def _compute_mounts(self):
        mounts = collections.OrderedDict()

        for source_path, dest_path in self._get_user_mounts().items():
            full_dest_path = os.path.join(self.path, dest_path)
            mounts[os.path.abspath(source_path)] = full_dest_path

        if self._use_run_shm:
            shm_source_path = "/run/shm"
        else:
            shm_source_path = "/dev/shm"

        system_source_paths = ["/dev",
                               "/dev/pts",
                               "/sys",
                               "/proc",
                               "/tmp",
                               "/var/run/dbus",
                               "/run/udev",
                               shm_source_path]

        for source_path in system_source_paths:
            if os.path.exists(source_path):
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
            if dest_path not in mounted:
                if os.path.exists(dest_path):
                    check_call(["mount", "--bind", source_path, dest_path])

        self._setup_dns()

    def setup_xauth(self):
        source_path = os.environ["XAUTHORITY"]
        dest_path = os.path.join(self.path, "home", self._user_name,
                                 ".Xauthority")

        try:
            shutil.copyfile(source_path, dest_path)
            os.chown(dest_path, self._uid, self._gid)
        except IOError:
            pass

    def _setup_dns(self):
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

    def _install_npm_packages(self):
        npm_packages = self._config.get("npm_packages")
        if npm_packages:
            self.run("npm install -g %s" % " ".join(npm_packages),
                     as_root=True)

    def _install_pypi_packages(self):
        pypi_packages = self._config.get("pypi_packages")
        if pypi_packages:
            self.run("pip install --upgrade %s" % " ".join(pypi_packages),
                     as_root=True)

    def _install_os_packages(self):
        self._builder.update_packages()

        flat_packages = []
        for group in self._config["packages"].values():
            for package in group:
                if package not in flat_packages:
                    flat_packages.append(package)

        self._builder.install_packages(flat_packages)

        if "sudo" in flat_packages:
            self._setup_sudo()

        self._install_npm_packages()
        self._install_pypi_packages()

    def _get_stamp_path(self):
        return self.path + ".stamp"

    def _check_exists(self, exists, message=True):
        if exists:
            if not os.path.exists(self.path):
                if message:
                    print("You must create or download the build root first.")
                return False
        else:
            if os.path.exists(self.path):
                if message:
                    print("The build root already exists.")
                return False

        return True

    def create(self, arch=None, mirror=None):
        if not self._check_exists(False):
            return False

        try:
            os.makedirs(self.path)
        except OSError:
            pass

        self._builder.create(arch, mirror)

        self._setup_system()
        self._setup_user()

        self.activate()
        try:
            self._install_os_packages()
            self._builder.clean_packages()
        finally:
            self.deactivate()

        self._touch_stamp()

        return True

    def setup(self):
        broot_exists = self._check_exists(True, message=False)
        broot_valid = self._check_stamp()

        if not broot_exists or not broot_valid:
            if not self._download():
                return False

        self.activate()
        try:
            self._install_os_packages()
        finally:
            self.deactivate()

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

    def get_arch(self):
        arch = check_output(["uname", "-m"]).strip()

        if arch == "i686":
            arch = "i386"

        return arch

    def _download(self):
        prebuilt_name = self._config["prebuilt"]["name"]
        prebuilt_url = self._config["prebuilt"]["url"]

        last_url = "%slast-%s-%s" % (prebuilt_url, self.get_arch(),
                                     prebuilt_name)

        try:
            last = urllib2.urlopen(last_url).read().strip()
        except:
            print "Failed to download %s" % last_url
            raise

        try:
            os.makedirs(self._var_dir)
        except OSError:
            pass

        os.chdir(self._var_dir)

        tar_filename = wget.download(prebuilt_url + last)
        if tar_filename is None:
            return False

        from_path = "%s-.{%d}" % (self.path[1:self.path.rindex("-")],
                                  self._hash_len)
        to_path = os.path.basename(self.path)

        result = call("tar --xz --numeric-owner -p "
                      "--transform 's,^%s,%s,x' -xf %s" %
                      (from_path, to_path, tar_filename), shell=True)

        os.unlink(tar_filename)

        print ""

        if result != 0:
            return False

        self._touch_stamp()

        return True

    def distribute(self):
        if not self._check_exists(True):
            return False

        name = self._config["name"]

        check_call(["tar", "cvfJ", "%s-broot.tar.xz" % name, self.path])

        return True

    def run(self, command, as_root=False):
        if not self._check_exists(True):
            return False

        if as_root:
            chroot_command = "chroot"
        else:
            chroot_command = "chroot --userspec %d:%d" % (self._uid, self._gid)

        self.activate()
        try:
            if not as_root:
                self.setup_xauth()

            env = {"LANG": "C",
                   "PATH": "/bin:/usr/bin:/usr/sbin"}
            to_keep = ["http_proxy", "https_proxy"]

            if as_root:
                env["HOME"] = "/root"
            else:
                home_dir = "/home/%s" % self._user_name

                env["HOME"] = home_dir
                env["XAUTHORITY"] = os.path.join(home_dir, ".Xauthority")
                env["BROOT"] = "yes"

                to_keep.extend(["DISPLAY", "XAUTHLOCALHOSTNAME", "TERM"])

            for name in to_keep:
                if name in os.environ:
                    env[name] = os.environ[name]

            env_string = ""
            for name, value in env.items():
                env_string += "%s=%s " % (name, value)

            result = call("%s %s /usr/bin/env -i %s /bin/bash -lc \"%s\"" %
                          (chroot_command, self.path, env_string, command),
                          shell=True)

            return result == 0
        finally:
            self.deactivate()

        return True

    def _check_stamp(self):
        try:
            with open(self._get_stamp_path()) as f:
                stamp = f.read()
        except IOError:
            stamp = ""

        return stamp == self._config.get("stamp", "")

    def _touch_stamp(self):
        with open(self._get_stamp_path(), "w") as f:
            stamp = self._config.get("stamp", "")
            f.write(stamp)
            f.close()

    def _create_user(self):
        self.run("/usr/sbin/groupadd %s --gid %d" %
                 (self._user_name, self._gid), as_root=True)

        self.run("/usr/sbin/useradd %s --uid %d --gid %d" %
                 (self._user_name, self._gid, self._uid), as_root=True)

    def _setup_system(self):
        dirs_to_make = ["var/run/dbus", "run/udev"]

        if self._use_run_shm:
            dirs_to_make.append("run/shm")

        try:
            for path in dirs_to_make:
                os.makedirs(os.path.join(self.path, path))
        except OSError:
            pass

        self._create_user()

    def _setup_user(self):
        to_chown = []

        shell_path = self._config.get("shell_path", None)
        if shell_path:
            bashrc_path = os.path.join(self.path, "home", self._user_name,
                                       ".bashrc")

            with open(bashrc_path, "w") as f:
                f.write("cd %s" % shell_path)

            to_chown.append(bashrc_path)

        try:
            for path in self._get_user_mounts().values():
                full_path = os.path.join(self.path, path)
                os.makedirs(full_path)
                to_chown.append(full_path)
        except OSError:
            pass

        for path in to_chown:
            os.chown(path, self._uid, self._gid)

    def _setup_sudo(self):
        sudoers_path = os.path.join(self.path, "etc", "sudoers")

        with open(sudoers_path) as f:
            conf = f.read()

        line = "\n%s ALL=(ALL:ALL) NOPASSWD:ALL"
        if line not in conf:
            conf = conf + line % self._user_name

        with open(sudoers_path, "w") as f:
            f.write(conf)
