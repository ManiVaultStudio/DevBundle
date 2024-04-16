#!/usr/bin/env python3
import argparse
import json
from utils.configclasses import Config
from argparse import RawDescriptionHelpFormatter
from pathlib import Path


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
    with open(args.cfg_file) as cp:
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
    with open(args.cfg_file) as cp:
        config_input = json.load(cp)
        configs = get_config_dict(config_input)
        config = configs.get(args.config_name, None)
        if config is None:
            print(f"Configuration named: {args.config_name} was not found")
            return
        config.use(args.skip_binary, args.ssh, args.mode, args.cmake, args.define_cmake_var, args.shallow)


if __name__ == "__main__":
    common = argparse.ArgumentParser(
        prog="dev_hdps",
        add_help=False,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    common.add_argument(
        "--cfg_file",
        type=str,
        default="config.json",
        help="Provide an alternate bundle configuration file, the default file is config.json",
    )
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    subparsers = parser.add_subparsers(
        help="Commands to list and use the defined environments"
    )

    parser_list = subparsers.add_parser(
        "list", help="List all ManiVault development configurations", parents=[common]
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
        parents=[common],
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser_use.add_argument(
        "config_name",
        type=str,
        default=None,
        help="The name of the configuration to retrieve",
    )
    parser_use.add_argument(
        "--mode",
        choices=["clean", "cmake_only", "update_only"],
        default="clean",
        help="""
modes behaviours are are follows:

    clean (the default): Delete and then clone all the repo directories.
    cmake_only: Leave the repos as-is and only recreate the top-level cmake.
    update_only: Run git pull to update al the repos in the bundle. Errors may occur
            if there are local changes. These have to be resolved manually.
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
        "--define_cmake_var", "-D",
        action="append",
        nargs=2,
        metavar=("VAR_NAME", "VAR_VALUE"),
        default=[],
        help="""
Define a cmake variable that should be visible in all subprojects. 
The subproject then may or may not make use of the variable, e.g.
--define_cmake_var MV_UNITY_BUILD ON --define_cmake_var MV_USE_AVX OFF
        """,
    )
    parser_use.add_argument(
        "--ssh",
        action="store_true",
        help="Use SSH (instead of the default http) for git access",
    )
    parser_use.add_argument(
        "--cmake",
        action="store_true",
        help="Run cmake-gui after the use command, cmake-gui needs to be on the path",
    )
    parser_use.add_argument(
        "--shallow",
        action="store_true",
        help="Causes a git shallow (depth=1) clone, can help when network delays are an issue",
    )
    parser_use.set_defaults(func=use)
    parser.epilog = (
        "--- Common arguments for list,use ---"
        + common.format_help().replace(common.format_usage(), "")
        + """ 
Purpose: Create and manage a ManiVault development environment.

        A ManiVault development environment is a directory containing a top-level
        CMakeLists.txt file to create a single project from the ManiVault core and
        a selection of plugins. The core and plugins are in subdirectories.
        This is useful way to work when you need to edit/build multiple
        plugins and the core on a development branch.

        Development environments are defined in the config.json file or a 
        user supplied configuration.
        """
    )
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        exit(1)
    args.func(args)
