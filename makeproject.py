#!/usr/bin/env python3
import argparse
import json
from utils.configclasses import Config
from argparse import RawDescriptionHelpFormatter


def get_config_dict(config_input: dict) -> dict:
    configs = {}
    repo_info = config_input.get("repo_info", {})
    binary_config = config_input.get("prebuilt_binaries", {})
    for build_config in config_input["build_bundles"]:
        c = Config(build_config, repo_info, binary_config)
        configs[c.name] = c
    return configs


def list(args: argparse.Namespace):
    """Implement the list subcommand

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments for the list subcommand.
    """
    with open("config.json") as cp:
        config_input = json.load(cp)
        configs = get_config_dict(config_input)
        if args.config_name == "":
            for config in configs:
                print(config)
        else:
            res_str = str(configs.get(args.config_name, "Not found"))
            print(res_str)


def use(args: argparse.Namespace):
    """Implement the use subcommand

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments for the use subcommand.
    """
    with open("config.json") as cp:
        config_input = json.load(cp)
        configs = get_config_dict(config_input)
        config = configs.get(args.config_name, None)
        if config is None:
            print(f"Configuration named: {args.config_name} was not found")
            return
        config.use(args.skip_binary, args.ssh, args.mode)


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
        "config_name",
        type=str,
        default="",
        nargs="?",
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
        "--mode",
        choices=["clean", "cmake_only", "develop"],
        default="clean",
        help="""
modes behaviours are are follows:

    clean (the default): Delete and then clone all the repo directories.
    cmake_only: Leave the repos as-is and only recreate the top-level cmake.
    develop: Intended for developer, change preserving, details T.B.D.
        """,
    )
    parser_use.add_argument(
        "--skip_binary",
        action="append",
        default=[],
        help="""
If you prefer to use your own versions
skip specific 3-party binaries. e.g.
--skip_binary QT5152 --skip_binary FreeImage3180
        """,
    )
    parser_use.add_argument(
        "--ssh",
        action="store_true",
        help="Use SSH (instead of the default http) for git access",
    )
    parser_use.set_defaults(func=use)
    args = parser.parse_args()
    args.func(args)
