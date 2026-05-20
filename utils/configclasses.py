import os
import sys
import json
import platform
import shutil
import re
import subprocess
import requests
import tarfile
from dataclasses import dataclass, field
from typing import TypedDict, Self
from git import Repo, GitCommandError
from git.remote import RemoteProgress
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional
from deepdiff import DeepDiff


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


def get_system_name() -> str:
    system_name = "Windows"
    if platform.system() == "Darwin":
        system_name = "Macos"
    if platform.system() == "Linux":
        system_name = "Linux"
    return system_name


class Binary:
    """
    The detailed configuration for a prebuilt binary
    including the associated cmake variables.
    Largely a wrapper for the dictionary that supports

    """

    def __init__(self, name: str, binary_config: dict, bin_root: Path):
        self.name = name
        self.config = binary_config
        self.bin_root = bin_root

    def __str__(self) -> str:
        result = f"Binary: {self.name}"
        result += f"\n Url: {self.bin_url}"
        result += f"\n BinPath: {self.bin_path}"
        cmake_vars = self.cmake_variables
        result += f"\n CMake variables: "
        for var_tup in cmake_vars:
            result += f"\n\t {var_tup[0]}: {var_tup[1]}"
        return result

    def _abs_path(self, path: str) -> str:
        new_path = path
        if path.startswith("+"):
            new_path = str(
                Path(
                    self.bin_root,
                    self.name,
                    path[1:],
                )
            ).replace("\\", "/")
        return new_path

    @property
    def cmake_variables(self) -> List[tuple]:
        """
        Retun a list of tuples of CMake var name and value

        The config can have a sequence of common cmake_variables
        and system specific cmake_variables: cmake_variables_<SYSTEM>,
        <SYSTEM> is one of Windows, Macos or Linux.

        Where the variable name is both in common and system specific
        the system specific variable over writes the common value
        """
        var_dict = dict()
        system_name = get_system_name()
        specific_variables = f"cmake_variables_{system_name}"

        if "cmake_variables" in self.config:
            for variable_name in self.config["cmake_variables"].keys():
                variable_value = self._abs_path(
                    self.config["cmake_variables"][variable_name]
                )
                var_dict[variable_name] = [variable_value]

        if specific_variables in self.config:
            for variable_name in self.config["cmake_variables"].keys():
                variable_value = self._abs_path(
                    self.config[specific_variables][variable_name]
                )
                var_dict[variable_name] = [variable_value]

        variables: list[tuple] = []
        for var_name in var_dict:
            variables.append((var_name, var_dict[var_name]))

        bin_path = self.config.get("bin_path", None)
        if bin_path:
            variable_value = self.config["bin_path"]
            if variable_value.startswith("+"):
                variable_value = str(
                    Path(
                        self.bin_root,
                        self.name,
                        variable_value[1:],
                    )
                ).replace("\\", "/")
            variables.append((None, variable_value))
        return variables

    @property
    def bin_url(self) -> str:
        """
        Returns the url that can be used to fetch the package from artifactory
        """
        system_name = get_system_name()
        system_binaries = self.config["binaries"]
        return system_binaries.get(system_name, "T.B.D")

    @property
    def bin_path(self) -> str:
        """
        Returns an absolute bin path
        """
        system_name = get_system_name()
        system_binary_path = f"bin_path_{system_name}"
        return self._abs_path(
            self.config.get(system_binary_path, self.config["bin_path"])
        )


class BinaryDict(TypedDict):
    name: str
    binary: Binary


class Binaries:
    """A class holding configuration for a pre-built binary
    provides logic to unpack the binary an return the CMake variable
    names and values.
    """

    JfrogReadToken = "cmVmdGtuOjAxOjAwMDAwMDAwMDA6OGV4QnVZcmR0S2piU0RSWTJTbjRRQTMxYkRh"

    def __init__(self, binary_configs: dict, bin_root: Path, in_factory: bool = False):
        self.raw_config = binary_configs
        self.binaries = BinaryDict()
        self.bin_root = bin_root
        if not in_factory:
            for name in binary_configs:
                self.binaries[name] = Binary(name, binary_configs[name], bin_root)

    def __str__(self) -> str:
        """Get a readable string version of the binary info configuration.

        Returns
        -------
        str
            The readable string
        """
        result = ""
        for bin_name in self.binaries:
            result += f"\n\n {str(self.binaries[bin_name])}"

        return result

    def get_subset(self, names: List[str]):
        subset = Binaries(self.raw_config, self.bin_root, in_factory=True)
        for name in names:
            subset.binaries[name] = Binary(name, self.raw_config[name], self.bin_root)
        return subset

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
            headers={"X-Jfrog-Art-Api": f"{Binaries.JfrogReadToken}"},
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

    def use_binary(self, bin_name: str):
        if bin_name not in self.raw_config:
            raise RuntimeError(
                f"{bin_name} is not a defined binary - check the config file for errors"
            )
        binary = self.binaries[bin_name]
        bin_url = binary.bin_url
        if bin_url is not None:
            print(f"Downloading {bin_name}")
            tar_path = self.download(bin_name, bin_url)
            print(f"Downloaded: {tar_path}")
            self.unpack(tar_path, bin_name)

    def get_cmake_variables(self, bin_name: str):
        variables = self.binaries[bin_name].cmake_variables
        return variables


class ManiVaultRepo:
    """A class holding the configuration of a ManiVault related repo"""

    mv_repo_root = "https://github.com/ManiVaultStudio/"
    mv_repo_root_ssh = "git@github.com:ManiVaultStudio/"

    def __init__(
        self, repo_config: dict, repo_info: dict, default_branch: str = "main"
    ):
        self.enabled = not repo_config.get("disable", False)
        self.repo_url = f"{self.mv_repo_root}{repo_config['repo']}"
        self.repo_ssh = f"{self.mv_repo_root_ssh}{repo_config['repo']}.git"
        self.repo_local = None
        # Local allow the user to configure a local path
        if "local" in repo_config:
            self.repo_local = repo_config["local"]

        self.repo_name = repo_config["repo"]
        self.__binaries = []
        if self.repo_name in repo_info:

            if "binaries" in repo_info[self.repo_name]:
                self.__binaries = repo_info[self.repo_name]["binaries"]

        if "tag" in repo_config:
            self.branch = repo_config.get("tag")
        else:
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
            print(f"Checking for changes: {Path(source_dir, self.repo_name)}")
            if Path(self.repo_name).exists():
                repo = Repo(self.repo_name)
                dirty = repo.is_dirty(untracked_files=True)
        finally:
            os.chdir(curdir)
        return dirty

    def use(self, mode="clean", ssh=False, shallow=False):
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
        shallow: bool, optional
            Do a shallow (depth=1) git clone
        """
        if mode == "cmake_only":
            return
        if self.repo_local:  # A local repo does not need to be cloned
            return
        try:
            if Path(self.repo_name).exists():
                repo = Repo(self.repo_name)
                print(f"Checkout: {self.repo_name}: {self.branch}")
                repo.git.checkout(self.branch)
            else:
                multi_options = ["--recurse-submodules"]
                if shallow:
                    multi_options.append("--depth=1")
                source = self.repo_url if not ssh else self.repo_ssh
                print(f"Cloning {self.repo_name} ({self.branch}) from: {source}")
                Repo.clone_from(
                    source,
                    to_path=self.repo_name,
                    branch=self.branch,
                    multi_options=multi_options,
                    progress=Progress(),
                )
        except GitCommandError as ex:
            print(f"git command failed due to {str(ex)}")
            raise UserWarning(f"git command failed\n{str(ex)}")

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
                except GitCommandError as ex:
                    # Handling consists of informing the user
                    print(f"git pull failed due to: {str(ex)}")
                    raise UserWarning(
                        f"git pull {self.repo_name} failed due to: {str(ex)}"
                    )
        finally:
            os.chdir(curdir)

    # handle it


class Config:
    """A development configuration comprising multiple ManiVault
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
        self.repos = []

        if "mv_repos" in build_config:
            for repo_config in build_config["mv_repos"]:
                repo = ManiVaultRepo(repo_config, common_dependencies)
                if repo.enabled:
                    self.repos.append(repo)

        # old naming, kept for backwards compatibility
        if "hdps_repos" in build_config:
            for repo_config in build_config["hdps_repos"]:
                repo = ManiVaultRepo(repo_config, common_dependencies)
                if repo.enabled:
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
        res_str += "mv_repos: \n"
        for repo in self.repos:
            res_str += "\t" + str(repo) + "\n"

        # Get all the binaries used by the
        # repos in this config
        binaries_set: set[str] = set()
        for repo in self.repos:
            binaries_set = binaries_set | set(repo.binaries)

        used_binaries = self.binaries.get_subset(binaries_set)
        res_str += str(used_binaries)
        return res_str

    def _get_dirty_repo_list(self, source_dir) -> List[ManiVaultRepo]:
        dirty: List[ManiVaultRepo] = []
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
        cmake_user_vars: List[str] = [],
        shallow: bool = False,
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
        cmake: bool, optional
            start the cmake gui on the build dir on completion
        cmake_user_vars: list(str), optional
            define cmake variables for all subprojects
        shallow: bool, optional
            do shallow (depth=1) git clones
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
        # and any binaries they need
        for repo in self.repos:
            repo.use(mode, ssh, shallow)
            binaries = binaries | set(repo.binaries)

        # skip user-defined binaries
        binaries = binaries.difference(skip_binaries)

        vcpkgBuilder = VcpkgJsonBuilder(self)
        vcpkgBuilder.create_merged_vcpg(self.name)

        # the setup returns cmake variables and values
        cmake_vars = []
        for binary in binaries:
            self.binaries.use_binary(binary)
            cmake_vars.extend(self.binaries.get_cmake_variables(binary))
        os.chdir(str(self.source_dir))

        self.cmakebuilder.make(cmake_vars, cmake, cmake_user_vars)


@dataclass
class ManualResolve:
    """Represents information over a dependency clash between two repos"""

    name: str
    repo_a: str
    constraint_a: dict
    repo_b: str
    constraint_b: dict

    def __str__(self) -> str:
        def fmt(repo, constraint):
            if not constraint:
                return f"  {repo}: (no version constraint)"
            parts = ", ".join(f"{k}: {v}" for k, v in constraint.items())
            return f"  {repo}: {parts}"

        return (
            f"VERSION CLASH: {self.name}\n"
            f"{fmt(self.repo_a, self.constraint_a)}\n"
            f"{fmt(self.repo_b, self.constraint_b)}"
        )


def input_choice(preamble: str, options: list[str], postamble: str = ""):
    prompt = preamble + " \n"
    for pos, opt in enumerate(options, start=1):
        prompt += f"{pos}) {opt} \n"
    prompt += postamble

    while True:
        user_input = input(prompt)
        input_choice = int(user_input)
        if input_choice > 0 and input_choice <= len(options):
            return input_choice
        if input_choice == -1:
            return -1
        print(f"choose a value between 1 and {len(options)}")

@dataclass 
class Override:
    """Represents a vcpkg override"""

    name: str
    constraint: dict = field(default_factory=dict)
    source_repo: str = ""

    @classmethod
    def normalized_dict(cls, override: str | dict) -> dict:
        if isinstance(override, str):
            return {"name": override}
        return override
    
    @classmethod
    def create(cls, override: str | dict, source_repo: str) -> Self:
        constraint = Override.normalized_dict(override)
        name = constraint["name"]
        return Override(name, constraint, source_repo)
    
    def to_vcpkg(self) -> dict | str:
        if not self.constraint:
            return self.name
        return {"name": self.name, **self.constraint}
@dataclass
class Dependency:
    """Represents a vcpkg dependency"""

    name: str
    constraint: dict = field(default_factory=dict)
    source_repo: str = ""

    @classmethod
    def normalized_dict(cls, dep: str | dict) -> dict:
        if isinstance(dep, str):
            return {"name": dep}
        return dep

    @classmethod
    def create(cls, dep: str | dict, source_repo: str) -> Self:
        constraint = Dependency.normalized_dict(dep)
        name = constraint["name"]
        return Dependency(name, constraint, source_repo)

    def to_vcpkg(self) -> dict | str:
        if not self.constraint:
            return self.name
        return {"name": self.name, **self.constraint}

    def check_clash(self, other_dep: Self) -> ManualResolve | None:
        common_constraint_keys = set(self.constraint.keys()) & set(
            other_dep.constraint.keys()
        )
        for key in common_constraint_keys:
            diff = DeepDiff(self.constraint, other_dep.constraint, ignore_order=True)
            if len(diff.affected_paths) > 0:
                if (
                    choice := input_choice(
                        f"Resolve the dependency clash between {self.source_repo} and"
                        f" {other_dep.source_repo}, \n"
                        f" {diff} on {self.constraint['name']}\n"
                        "choose one of the options below \n",
                        [
                            self.source_repo + ": " + str(self.constraint),
                            other_dep.source_repo + ": " + str(other_dep.constraint),
                        ],
                        "-1) to manually unresolved later: ",
                    )
                ) == -1:
                    return ManualResolve(
                        self.name,
                        self.source_repo,
                        self.constraint,
                        other_dep.source_repo,
                        other_dep.constraint,
                    )
                else:
                    if choice == 2:
                        self.constraint = other_dep.constraint
                        self.source_repo = other_dep.source_repo

        return None


class VcpkgJsonBuilder:
    """For vcpkg support - build a vcpkg.json that is the
    union of the vcpkg.json dependencies in all the
    repos."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.vcpkgpath = Path(config.build_dir, "vcpkg.json")
        self.sourcepath = config.source_dir
        self.vcpkgFiles = self.__collect_source_dirs()

    def __collect_source_dirs(self) -> List[Path]:
        vckpgList = self.sourcepath.glob("**/vcpkg.json")
        return vckpgList

    def __merge_repo_vcpkgs(self, name: str):
        merged_dependencies: dict[str, Dependency] = {}
        merged_overrides: dict[str, Override] = {}
        manual_resolves: list[ManualResolve] = []
        for manifest_path in self.vcpkgFiles:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"  ERROR: Failed to parse {manifest_path}: {e}")
                sys.exit(1)

            raw_deps = manifest.get("dependencies", [])
            print(f"  {manifest_path.parent.stem}: found {len(raw_deps)} dependencies")
            source_repo = manifest_path.parent.stem

            for raw_dep in raw_deps:
                dep = Dependency.create(raw_dep, source_repo)

                # Skip internal libs — they are built via add_subdirectory
                # This filters any internal libs - not sure if it's relevant
                # if name in internal_names:
                #    continue

                if dep.name not in merged_dependencies:
                    merged_dependencies[dep.name] = dep
                else:
                    existing = merged_dependencies[dep.name]
                    if manual_resolve := existing.check_clash(dep):
                        manual_resolves.append(manual_resolve)
                    else:
                        # No clash — use whichever has a constraint (more specific wins)
                        if dep.constraint and not existing.constraint:
                            merged_dependencies[dep.name].constraint = dep.constraint
                            merged_dependencies[dep.name].source_repo = dep.repo

            raw_overrides = manifest.get("overrides", [])
            print(f"  {manifest_path.parent.stem}: found {len(raw_deps)} overrides")
            for raw_override in raw_overrides:
                override = Override.create(raw_override, source_repo)
                merged_overrides[override.name] = override

        bundle_manifest = {
            "name": f"{name}",
            "version": "0.1.0",
            "dependencies": [
                dep.to_vcpkg()
                for dep in sorted(merged_dependencies.values(), key=lambda d: d.name)
            ],
            "overrides" : [
                override.to_vcpkg()
                for override in sorted(merged_overrides.values(), key=lambda d: d.name)
            ]
        }
        return bundle_manifest, manual_resolves

    def create_merged_vcpg(self, name: str):
        manifest, manual_resolves = self.__merge_repo_vcpkgs(name)
        if len(manual_resolves) > 0:
            print("\n" + "=" * 60)
            print(
                f"FOUND {len(manual_resolves)} VERSION CLASH(ES) — bundle manifest NOT written."
            )
            print("=" * 60)
            for resolve in manual_resolves:
                print(f"\n{json.dumps(resolve.constraint_a)}")
                print(f"\n{json.dumps(resolve.constraint_b)}")
            print("\nResolve clashes by aligning version constraints in the")
            print("affected sub-repo vcpkg.json files before re-running.")

        self.vcpkgpath.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )


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
                int(re.match(r"\.(\d{3})", x.suffix).group(1))
                for x in files
                if re.match(r"\.\d{3}", x.suffix) is not None
            ]
        )
        # Create the next version number
        version_num = 0
        if len(versions) > 0:
            version_num = versions[-1] + 1
        # Rename the existing CMakeLists.txt to CmakeLists.nnn
        cmakepath = Path(".", "CMakeLists.txt")
        cmakepath.rename(f"CMakeLists.{version_num:03}")

    def make(
        self, cmake_vars: List[tuple], cmake: bool, cmake_user_vars: List[str]
    ) -> None:
        self.save_numbered_cmakefile()
        print(f"Making {self.cmakelistspath}")
        with open(str(self.cmakelistspath), "a") as cf:
            cf.write("cmake_minimum_required(VERSION 3.22)\n")
            cf.write(f"\nproject({self.config.name})\n\n")
            mv_install_dir = str(self.config.install_dir.resolve()).replace("\\", "/")
            cf.write(
                f"""set(MV_INSTALL_DIR "{mv_install_dir}" CACHE PATH "Path where the MV core and plugins are installed")
\n"""
            )
            bin_paths = []

            # cmake variables by dependencies
            for setting in cmake_vars:
                if setting[0] is None:
                    bin_paths.append(setting[1])
                else:
                    # if name ends with + this is a list to append
                    if setting[0][-1] == "+":
                        cf.write(
                            f"list(APPEND {setting[0][:-1]} {' '.join(setting[1])})\n"
                        )
                    else:
                        cf.write(
                            f'set({setting[0]} {";".join(setting[1])} CACHE PATH "")\n'
                        )

            # cmake variables added by user with --define_cmake_var
            for setting in cmake_user_vars:
                if len(setting) != 2:
                    continue
                if setting[1] in ["TRUE", "FALSE", "ON", "OFF"]:
                    cf.write(f'set({setting[0]} {setting[1]} CACHE BOOL "")\n')
                else:
                    cf.write(f'set({setting[0]} {setting[1]} CACHE PATH "")\n')

            if len(cmake_user_vars) >= 1:
                cf.write("\n")

            for repo in self.config.repos:
                if repo.repo_local:
                    # must add a binary dir if the repo is not in the tree
                    Path(".").parent
                    cf.write(
                        f"add_subdirectory({repo.repo_local}"
                        f" {Path(Path('.').resolve().parent, 'build', repo.repo_name).as_posix()})\n"
                    )
                else:
                    cf.write(f"add_subdirectory({repo.repo_name})\n")
            cf.write("\n")
            cf.write(
                "set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY"
                " VS_STARTUP_PROJECT MV_Application)\n"
            )
            # print(f"******** CMAKE bin paths + cmake_vars {bin_paths} {cmake_vars} ***********")
            if len(bin_paths) > 0:
                cf.write(
                    "set_target_properties(MV_Application PROPERTIES"
                    f" VS_DEBUGGER_ENVIRONMENT \"PATH=%PATH%;{';'.join(bin_paths)}\")\n"
                )
            cf.write("\n")

        if cmake:
            print(
                f"Starting Cmake GUI source {self.config.source_dir} build"
                f" {self.config.solution_dir}"
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
