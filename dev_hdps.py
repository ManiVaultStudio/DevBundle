#!/usr/bin/env python3
import argparse
import json
import os
import shutil
from argparse import RawDescriptionHelpFormatter
from git import Repo
from git.remote import RemoteProgress
from pathlib import Path

hdps_repo_root = "https://github.com/hdps/"


class Progress(RemoteProgress):
    def update(self, op_code, cur_count, max_count=None, message=""):
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
    def __init__(self, repo_config: dict, default_branch: str = None):
        self.repo_url = f"{hdps_repo_root}{repo_config['repo']}"
        self.repo_name = repo_config["repo"]
        self.branch = repo_config.get("branch", default_branch)

    def __str__(self):
        return f"repo: {self.repo_url},\tbranch: {self.branch}"

    def use(self, force=False, stash=False):
        print(f"Cloning from: {self.repo_url}")
        Repo.clone_from(
            self.repo_url,
            to_path=self.repo_name,
            branch=self.branch,
            progress=Progress(),
        )


class Config:
    def __init__(self, build_config: dict):
        self.name = build_config["name"]
        self.build_dir = build_config["build_dir"]
        self.branch = build_config.get("branch", None)
        self.repos = []
        self.branch = build_config.get("branch", None)
        for repo_config in build_config["hdps_repos"]:
            repo = HdpsRepo(repo_config)
            self.repos.append(repo)

    def __str__(self):
        res_str = f"name: {self.name}\n"
        res_str += f"build dir: {self.build_dir}\n"
        if self.branch is not None:
            res_str += f"branch: {self.branch}\n"
        res_str += "hdps_repos: \n"
        for repo in self.repos:
            res_str += "\t" + str(repo) + "\n"
        return res_str

    def use(self, clean=True, force=False, stash=False):
        if clean and Path(self.build_dir).exists():
            shutil.rmtree(self.build_dir, onerror=onerror)
        if not Path(self.build_dir).exists():
            Path(self.build_dir).mkdir()
        os.chdir(self.build_dir)
        for repo in self.repos:
            repo.use(force, stash)


def get_config_dict(config_input: dict) -> dict:
    configs = {}
    for build_config in config_input["build_configs"]:
        c = Config(build_config)
        configs[c.name] = c
    return configs


def list(args: argparse.Namespace):
    with open("config.json") as cp:
        config_input = json.load(cp)
        configs = get_config_dict(config_input)
        if args.config_name is None:
            for config in configs:
                print(config)
        else:
            res_str = str(configs.get(args.config_name, "Not found"))
            print(res_str)


def use(args: argparse.Namespace):
    with open("config.json") as cp:
        config_input = json.load(cp)
        configs = get_config_dict(config_input)
        config = configs.get(args.config_name, None)
        if config is None:
            print(f"Configuration named: {args.config_name} was not found")
            return
        config.use(args.clean, args.force, args.stash)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="dev_hdps",
        add_help=True,
        description="""
        Create and manage an HDPS development environment.

        An HDPS development environment is a directory containing a top-level
        CMakeLists.txt file to create a single project from the HDPS core and
        a selection of plugins. The core and plugins are in subdirectories.
        This is useful way to work when you need to edit/build multiple
        plugins and the core on a development branch.

        Development environments are defined in the config.json file.
        This repo has two default configurations but you can add more.
        Each configuration can have a separate directory or
        reuse the default directory defined at the top of file.

        A relative path is relative to this repo directory otherwise use
        paths from the root of your file-system.
        """,
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    subparsers = parser.add_subparsers(
        help="Commands to list and use the defined environments"
    )

    parser_list = subparsers.add_parser(
        "list", help="List all HDPS development configurations"
    )
    parser_list.add_argument(
        "--config_name",
        type=str,
        default=None,
        help="List the details of the specific configuration",
    )
    parser_list.set_defaults(func=list)

    parser_use = subparsers.add_parser(
        "use",
        help="Use a development configuration (pulls the latest see options force & stash)",
    )
    parser_use.add_argument(
        "config_name",
        type=str,
        default=None,
        help="The name of the configuration to retrieve",
    )
    parser_use.add_argument(
        "--clean",
        default=True,
        help="Delete and recreate the directory, the default behavior",
    )
    parser_use.add_argument(
        "--force",
        default=False,
        help="Force overwritting any changes in the hdps subproject directories",
    )
    parser_use.add_argument(
        "--stash",
        default=False,
        help="Stash any changes in the hdps subproject directories",
    )
    parser_use.set_defaults(func=use)
    args = parser.parse_args()
    args.func(args)
