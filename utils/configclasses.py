import os
import platform
import shutil
import re
import subprocess
import requests
import tarfile
from git import Repo
from git.remote import RemoteProgress
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional


class Progress(RemoteProgress):
    """Support class to display progress of git operations

    Parameters
    ----------
    RemoteProgress : git.remote.RemoteProgress
        The base git progress implementation
    """

    def update(self, op_code, cur_count, max_count=None, message=""):
        """Provide feedback to the user on the git operation"""
        print(self._cur_line, end="\r")
        if op_code & self.END:
            print("\n")


def onerror(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.
    This happens on Windows removing the .git dir.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=onerror)``

    (Thank you stackoverflow! https://stackoverflow.com/a/2656405/584201)
    """
    import stat

    # Is the error an access error?
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


class Binaries:
    """A class holding configuration for a pre-built binary
    provides logic to unpack the binary an return the CMake variable
    names and values.
    """

    def __init__(self, binary_config: dict, bin_root: Path):
        self.config = binary_config
        self.bin_root = bin_root

    def get_bin_names(self) -> List[str]:
        return list(self.config.keys())

    def get_bin_info(self, bin_name: str) -> dict:
        if bin_name not in self.config:
            raise RuntimeError(
                f"{bin_name} is not a defined binary - check the config file for errors"
            )
        return self.config[bin_name]

    def download(self, name: str, url: str) -> Path:
        if not self.bin_root.exists():
            self.bin_root.mkdir(parents=True)
        os.chdir(str(self.bin_root))
        local_name = f"{name}.tgz"
        if Path(".", local_name).exists():
            return Path(".", local_name).resolve()
        pemPath = Path(Path(__file__).parents[0], "artifactory.pem")
        with requests.get(
            url,
            stream=True,
            verify=pemPath,
            auth=("hdpsreader", "4ead0nlyAccess"),
        ) as req:
            req.raise_for_status()
            with open(f"{local_name}", mode="wb") as tarf:
                for chunk in req.iter_content(chunk_size=8192):
                    tarf.write(chunk)
        return Path(".", local_name).resolve()

    def unpack(self, tar_path: Path, name: str):
        """Binaries are unpacked to the directory given by bin_root + name
        If this directory exists the unpack is skipped

        Parameters
        ----------
        tar_path : Path
            full path to the binary tar files
        name : str
            binary name corresponding to the key in prebuilt_binaries in the config file
        """
        os.chdir(str(self.bin_root))
        if Path(".", name).exists():
            return
        Path(".", name).mkdir()
        os.chdir(name)
        tarfile.open(tar_path).extractall(".")

    def use_binary(self, bin_name: str, skip: bool = False) -> List[tuple]:
        if bin_name not in self.config:
            raise RuntimeError(
                f"{bin_name} is not a defined binary - check the config file for errors"
            )
        bin_info = self.config[bin_name]
        system = "Windows"
        if platform.system() == "Darwin":
            system = "Macos"
        bin_url = bin_info["binaries"][system]
        print(f"Downloading {bin_name}")
        tar_path = self.download(bin_name, bin_url)
        print(f"Downloaded: {tar_path}")
        self.unpack(tar_path, bin_name)
        variables: list[tuple] = []
        if "cmake_variables" not in bin_info:
            return variables

        # If a variable starts with + then the path to the binary dir is prepended
        # otherwise the variable gets the given value
        #
        # The variables tuple returned contains
        # 0) cmake variable name + 1) variable value (possibly a path)
        #
        # If there is a bin_path the last tuple can be
        # 0) None + 1) bin_path - bin paths are always prepended (?does this make sense?)

        for variable_name in bin_info["cmake_variables"].keys():
            if not skip:
                variable_value = bin_info["cmake_variables"][variable_name]
                if variable_value.startswith("+"):
                    variable_value = str(
                        Path(
                            self.bin_root,
                            bin_name,
                            variable_value[1:],
                        )
                    ).replace("\\", "/")
                variables.append((variable_name, variable_value))

        bin_path = bin_info.get("bin_path", None)
        if bin_path:
            variable_value = bin_info["bin_path"]
            if variable_value.startswith("+"):
                variable_value = str(
                    Path(
                        self.bin_root,
                        bin_name,
                        variable_value[1:],
                    )
                ).replace("\\", "/")
            variables.append((None, variable_value))
        return variables


class HdpsRepo:
    """A class holding the configuration of an HDPS related repo"""

    hdps_repo_root = "https://github.com/hdps/"
    hdps_repo_root_ssh = "git@github.com:hdps/"

    def __init__(self, repo_config: dict, repo_info: dict, default_branch: str = None):
        self.repo_url = f"{self.hdps_repo_root}{repo_config['repo']}"
        self.repo_ssh = f"{self.hdps_repo_root_ssh}{repo_config['repo']}.git"
        self.repo_local = None
        # Local allow the user to configure a local path
        if "local" in repo_config:
            self.repo_local = repo_config["local"]

        self.repo_name = repo_config["repo"]
        self.project_dependencies = {}
        self.__binaries = []
        if self.repo_name in repo_info:
            # Sometimes the project is a single entity with dependencies
            if "dependencies" in repo_info[self.repo_name]:
                self.project_dependencies[self.repo_name] = repo_info[self.repo_name][
                    "dependencies"
                ]
            # Sometimes it comprises named sub-projects each with dependencies
            if "sub_project_dependencies" in repo_info[self.repo_name]:
                for project in repo_info[self.repo_name]["sub_project_dependencies"]:
                    self.project_dependencies[project] = repo_info[self.repo_name][
                        "sub_project_dependencies"
                    ][project]

            if "binaries" in repo_info[self.repo_name]:
                self.__binaries = repo_info[self.repo_name]["binaries"]

        self.branch = repo_config.get("branch", default_branch)

    @property
    def binaries(self):
        return self.__binaries

    def __str__(self) -> str:
        """Get a readable string version of this repo configuration

        Returns
        -------
        str
            The readable string
        """
        res_str = f"repo: {self.repo_url},\n\t\tbranch: {self.branch}"
        if len(self.project_dependencies) > 0:
            for project in self.project_dependencies:
                res_str += f"\n\t\tproject: {project}\tdependencies: {' '.join(self.project_dependencies[project])}"
        else:
            print(f"\n\t\tproject_name: {self.repo_name}")
        if len(self.__binaries) > 0:
            res_str += f"\n\t\tbinaries: {' '.join(self.__binaries)}"
        return res_str

    def is_dirty(self, source_dir: Path):
        """Check that the repo has no changes that have not been
        committed or any untracked files.

        Params:
        -------
        source_dir: the root of the source e.e. parent directory of the cloned
        repositories. The directory is assumed to exist.

        Returns: False is there is any discrepancy
        """
        curdir = Path.cwd()
        dirty = False
        try:
            os.chdir(str(source_dir))
            print(f"Checking: {Path(source_dir, self.repo_name)}")
            if Path(self.repo_name).exists():
                repo = Repo(self.repo_name)
                dirty = repo.is_dirty(untracked_files=True)
        finally:
            os.chdir(curdir)
        return dirty

    def use(self, mode="clean", ssh=False):
        """Switch the build repo in the current directory
        to the latest configured branch. Changes can be
        forcibly overwritten or stashed. If changes are encountered
        without one of these options then the function will fail.

        Parameters
        ----------
        "mode" : str, optional
            Behaviour, by default clean
        ssh : bool, optional
            Use ssh for github access (instead of https)
        """
        if mode == "cmake_only":
            return
        if self.repo_local:  # A local repo does not need to be cloned
            return
        if Path(self.repo_name).exists():
            repo = Repo(self.repo_name)
            print(f"Checkout: {self.repo_name}:{self.branch}")
            repo.git.checkout(self.branch)
        else:
            source = self.repo_url if not ssh else self.repo_ssh
            print(f"Cloning from: {source}")
            Repo.clone_from(
                source,
                to_path=self.repo_name,
                branch=self.branch,
                multi_options=["--recurse-submodules"],
                progress=Progress(),
            )

    def update(self, source_dir, ssh):
        """Run git pull on this repo. This may raise a
        UserWarning exception

        Params
        ------
        source_dir: The repository directory parent
        ssh: To use ssh or not

        Returns
        -------
        None

        :raises UserException: To notify that the git pull failed.
        """
        curdir = Path.cwd()
        try:
            if self.repo_local:  # A local repo will not be updated
                return
            if Path(source_dir, self.repo_name).exists():
                os.chdir(Path(source_dir, self.repo_name))
                repo = Repo(".")
                print(f"Pulling latest: {self.repo_name}:{self.branch}")
                try:
                    repo.git.pull()
                except Exception as e:
                    # Handling consists of informing the user
                    print(f"git pull failed due to: {e.message}")
                    raise UserWarning(
                        f"git pull {self.repo_name} failed due to: {e.message}"
                    )
        finally:
            os.chdir(curdir)

    # handle it


class Config:
    """A development configuration comprising multiple HDPS
    repositories.
    """

    def __init__(
        self, build_config: dict, common_dependencies: dict, binary_config
    ) -> None:
        self.name = build_config["name"]
        self.build_dir = Path(
            Path(__file__).parents[1], build_config["build_dir"]
        ).resolve()
        # print(f"Build dir = {self.build_dir}")
        self.source_dir = Path(self.build_dir, "source")
        self.install_dir = Path(self.build_dir, "install")
        self.solution_dir = Path(self.build_dir, "build")
        self.bin_root = Path(Path(__file__).parents[1], "binaries")
        self.branch = build_config.get("branch", None)
        self.repos = []
        self.branch = build_config.get("branch", None)
        for repo_config in build_config["hdps_repos"]:
            repo = HdpsRepo(repo_config, common_dependencies)
            self.repos.append(repo)
        self.cmakebuilder = CMakeFileBuilder(self)
        self.binaries = Binaries(binary_config, self.bin_root)

    def __str__(self) -> str:
        """Get a readable string version of this configuration.

        Returns
        -------
        str
            The readable string
        """
        res_str = f"name: {self.name}\n"
        res_str += f"build dir: {self.build_dir}\n"
        if self.branch is not None:
            res_str += f"branch: {self.branch}\n"
        res_str += "hdps_repos: \n"
        for repo in self.repos:
            res_str += "\t" + str(repo) + "\n"
        return res_str

    def _get_dirty_repo_list(self, source_dir) -> List[HdpsRepo]:
        dirty: List[HdpsRepo] = []
        if not source_dir.exists():
            return dirty
        for repo in self.repos:
            if repo.is_dirty(source_dir):
                dirty.append(repo)
        return dirty

    def use(
        self,
        skip_binaries: List[str] = [],
        ssh: bool = False,
        mode: str = "clean",
        cmake: bool = False,
    ) -> None:
        """Switch all the repos to this configuration.
        Optionally clean everything first and reclone.
        Alternatively stash changes or force overwrite
        per repo.

        Parameters
        ----------
        skip_binaries: list(str), optional
            skip using these 3rd party binaries
        ssh: bool, optional
            use ssh for git authentication
        mode: str, optional
            default "clean"
            clean: remove existing repos
            cmake_only: leave all repos perform cmake only
            update_only: Perform git pull on all repos - to update.
                    May fail if there are local changes.
        """
        if mode == "update_only":
            errors = []
            for repo in self.repos:
                try:
                    repo.update(self.source_dir, ssh)
                except UserWarning as w:
                    errors.append(w)
            if len(errors) > 0:
                print("There were errors during the update")
                for e in errors:
                    print(e.message)

        if mode != "cmake_only":
            if mode == "clean" and self.build_dir.exists():
                dirty_repos = self._get_dirty_repo_list(self.source_dir)
                if len(dirty_repos) > 0:
                    print("\n***CHANGES PREVENT REPOSITORY CLEANING**")
                    print("========================================")
                    print("The following repos have local changes or untracked files:")
                    for repo in dirty_repos:
                        print(f"{repo.repo_name}")
                    print("Resolve these issues manually before running ")
                    return
                shutil.rmtree(self.build_dir, onerror=onerror)
            if not self.build_dir.exists():
                self.build_dir.mkdir(parents=True)
            if not self.source_dir.exists():
                self.source_dir.mkdir()
            if not self.install_dir.exists():
                self.install_dir.mkdir()
            if not self.solution_dir.exists():
                self.solution_dir.mkdir()
        os.chdir(str(self.source_dir))
        skip_binaries = set(skip_binaries)
        binaries: set[str] = set()
        # Get all the repos
        for repo in self.repos:
            repo.use(mode, ssh)
            binaries = binaries | set(repo.binaries)
        # and any binaries they need
        # the setup returns cmake variables and values
        cmake_vars = []
        for binary in binaries:
            cmake_vars.extend(self.binaries.use_binary(binary, binary in skip_binaries))
        os.chdir(str(self.source_dir))
        self.cmakebuilder.make(cmake_vars, cmake)


class CMakeFileBuilder:
    """Build a cmake file for the configuration"""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cmakelistspath = Path(".", "CMakeLists.txt")

    def save_numbered_cmakefile(self) -> None:
        """
        If a CMakeLists.txt already exists for the project
        save it with a .nnn (version number) suffix
        """
        if not self.cmakelistspath.exists():
            return
        files = Path(".").glob("CMakeLists.*")
        # Find existing version numbered CMakeLists.nnn files
        # and get a sorted list of the cersion numbers
        versions = sorted(
            [
                int(re.match("\.(\d{3})", x.suffix).group(1))
                for x in files
                if re.match("\.\d{3}", x.suffix) is not None
            ]
        )
        # Create the next version number
        version_num = 0
        if len(versions) > 0:
            version_num = versions[-1] + 1
        # Rename the existing CMakeLists.txt to CmakeLists.nnn
        cmakepath = Path(".", "CMakeLists.txt")
        cmakepath.rename(f"CMakeLists.{version_num:03}")

    def make(self, cmake_vars: List[tuple], cmake: bool) -> None:
        self.save_numbered_cmakefile()
        print(f"Making {self.cmakelistspath}")
        with open(str(self.cmakelistspath), "a") as cf:
            cf.write("cmake_minimum_required(VERSION 3.17)\n\n")
            cf.write(f"\nproject({self.config.name})\n")
            hdps_install_dir = str(self.config.install_dir.resolve()).replace("\\", "/")
            cf.write(
                f"""\n
if(NOT DEFINED ENV{{HDPS_INSTALL_DIR}})
    set(ENV{{HDPS_INSTALL_DIR}} "{hdps_install_dir}")
endif()\n\n"""
            )
            bin_paths = []
            for setting in cmake_vars:
                if setting[0] is None:
                    bin_paths.append(setting[1])
                else:
                    # if name ends with + this is a list to append
                    if setting[0][-1] == "+":
                        cf.write(f"list(APPEND {setting[0][:-1]} {setting[1]})\n")
                    else:
                        cf.write(f'set({setting[0]} {setting[1]} CACHE PATH "")\n')

            for repo in self.config.repos:
                if repo.repo_local:
                    # must add a binary dir if the repo is not in the tree
                    Path(".").parent
                    cf.write(
                        f"add_subdirectory({repo.repo_local} {Path(Path('.').resolve().parent, 'build', repo.repo_name).as_posix()})\n"
                    )
                else:
                    cf.write(f"add_subdirectory({repo.repo_name})\n")
            cf.write("\n")
            cf.write(
                "set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY VS_STARTUP_PROJECT HDPS)\n"
            )
            if len(bin_paths) > 0:
                cf.write(
                    f"set_target_properties(HDPS PROPERTIES VS_DEBUGGER_ENVIRONMENT \"PATH=%PATH%;{';'.join(bin_paths)}\")"
                )
            cf.write("\n")
            for repo in self.config.repos:
                for project in repo.project_dependencies:
                    cf.write(
                        f"add_dependencies({project} {' '.join(repo.project_dependencies[project])})\n"
                    )
        if cmake:
            print(
                f"Starting Cmake GUI source {self.config.source_dir} build {self.config.solution_dir}"
            )
            subprocess.run(
                [
                    "cmake-gui",
                    "-S",
                    f"{self.config.source_dir}",
                    "-B",
                    f"{self.config.solution_dir}",
                ]
            )
