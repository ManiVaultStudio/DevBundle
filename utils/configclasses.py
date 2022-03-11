import os
import shutil
import re
from git import Repo
from git.remote import RemoteProgress
from pathlib import Path


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


class HdpsRepo:
    """A class hoding the configuration of an HDPS related repo"""

    hdps_repo_root = "https://github.com/hdps/"

    def __init__(self, repo_config: dict, repo_info: dict, default_branch: str = None):
        self.repo_url = f"{self.hdps_repo_root}{repo_config['repo']}"
        self.repo_name = repo_config["repo"]
        self.project_dependencies = {}
        if self.repo_name in repo_info:
            # SOmetimes the project is a single entity with dependencies
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

        self.branch = repo_config.get("branch", default_branch)

    def __str__(self) -> str:
        """Get a readable string version of this repo configuration

        Returns
        -------
        str
            The readable string
        """
        res_str = f"repo: {self.repo_url},\tproject_name: {self.repo_name}\tbranch: {self.branch}"
        if len(self.project_dependencies) > 0:
            for project in self.project_dependencies:
                res_str += f"\n\t\tproject: {project}, dependencies: {' '.join(self.project_dependencies[project])}"
        return res_str

    def use(self, clean=False, stash=True):
        """Switch the build repo in the current directory
        to the latest configured branch. Changes can be
        forcibly overwritten or stashed. If changes are encountered
        without one of these options then the function will fail.

        Parameters
        ----------
        clean : bool, optional
            Forcibly overwrite changes, by default False
        stash : bool, optional
            Stash any changes, by default True
        """
        if Path(self.repo_name).exists():
            repo = Repo(self.repo_name)
            print(f"Checkout: {self.repo_name}:{self.branch}")
            repo.git.checkout(self.branch)
        else:
            print(f"Cloning from: {self.repo_url}")
            Repo.clone_from(
                self.repo_url,
                to_path=self.repo_name,
                branch=self.branch,
                multi_options=["--recurse-submodules"],
                progress=Progress(),
            )


class Config:
    """A development configuration comprising multiple HDPS
    repositories.
    """

    def __init__(self, build_config: dict, common_dependencies: dict) -> None:
        self.name = build_config["name"]
        self.build_dir = build_config["build_dir"]
        self.branch = build_config.get("branch", None)
        self.repos = []
        self.branch = build_config.get("branch", None)
        for repo_config in build_config["hdps_repos"]:
            repo = HdpsRepo(repo_config, common_dependencies)
            self.repos.append(repo)
        self.cmakebuilder = CMakeFileBuilder(self)

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

    def use(self, clean=False, stash=True) -> None:
        """Switch all the repos to this configuration.
        Optionally clean everything first and reclone.
        Alternatively stash changes or force overwrite
        per repo.

        Parameters
        ----------
        clean : bool, optional
            _description_, by default False
        stash : bool, optional
            _description_, by default False
        """
        if clean and Path(self.build_dir).exists():
            shutil.rmtree(self.build_dir, onerror=onerror)
        if not Path(self.build_dir).exists():
            Path(self.build_dir).mkdir()
        os.chdir(self.build_dir)
        for repo in self.repos:
            repo.use(clean, stash)
        self.cmakebuilder.make()


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

    def make(self) -> None:
        self.save_numbered_cmakefile()
        print(f"Making {self.cmakelistspath}")
        with open(str(self.cmakelistspath), "a") as cf:
            cf.write("cmake_minimum_required(VERSION 3.17)\n\n")
            cf.write(f"\nproject({self.config.name})\n")
            for repo in self.config.repos:
                cf.write(f"add_subdirectory({repo.repo_name})\n")
            cf.write("\n")
            for repo in self.config.repos:
                for project in repo.project_dependencies:
                    cf.write(
                        f"add_dependencies({project} {' '.join(repo.project_dependencies[project])})\n"
                    )
