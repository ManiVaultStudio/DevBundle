"""A collection of classes used to merge vcpkg.json files
    from the subdiretory projects into a single top-level
    vcpkg.json.

    Merging a number of vcpkg.json files translates, when looked at simply,
    to merging a number of python dictionaries which may contain clashes.
    This code take a pragmatic approach, it does not try to automatically
    resolve all the issues itself. Instead dependency clashes will 
    produce user prompts but other clashes may appear in the file.

    No all top level items in the vcpkg.json are covered just the ones 
    present in ManiVault projects at the time of creation.

    It is expected that this will need to be extended as more complex
    vcpkg.json files are encountered. A reasonable strategy in many cases
    may be to write duplicates to the output file and ask the user to
    resolve these manually.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict, Self
import json
from deepdiff import DeepDiff
from typing import List

class VcpkgBaselines:
    """Loads and provides utilities to manipulate and query
       the list of vcpkg baseline SHAs"""

    def __init__(self):
        self.baselines = json.loads(Path(Path(__file__).parent, "baselines.json").read_bytes())
        self.baseline_tag_dict = {d["tag"]: d["sha"] for d in self.baselines}
        self.baseline_sha_dict = {d["sha"]: d["tag"] for d in self.baselines}

    def get_latest_valid_baseline(self, sha_list: list[str]) -> str: 
        
        latest_date = "2000.01.01"
        latest_baseline = "" 
        known_shas = self.baseline_sha_dict.keys()
        for sha in sha_list:
            if sha in known_shas:
                if latest_date < self.baseline_sha_dict[sha]:
                  latest_date = self.baseline_sha_dict[sha]
                  latest_baseline = sha
            else:
                print(f"Unrecognized baseline encountered in a vcpkg.json {sha}")

        if latest_baseline == "":
            print("Using latest sha tag for vcpkg baseline")
            latest_baseline = self.baseline_sha_dict[list(known_shas)[-1]]

        return latest_baseline
            
             
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

    def __init__(self, build_dir: Path, source_dir: Path) -> None:
        self.vcpkgpath = Path(build_dir, "vcpkg.json")
        self.sourcepath = source_dir
        self.vcpkgFiles = self.__collect_source_dirs()
        self.baselines = VcpkgBaselines()

    def __collect_source_dirs(self) -> List[Path]:
        vckpgList = self.sourcepath.glob("**/vcpkg.json")
        return vckpgList

    def __merge_repo_vcpkgs(self, name: str):
        merged_dependencies: dict[str, Dependency] = {}
        merged_overrides: dict[str, Override] = {}
        all_features: dict[dict] = {}
        manual_resolves: list[ManualResolve] = []
        baseline_shas = []
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

            features = manifest.get("features", {})
            for feature in features.keys():
                all_features[feature] = features[feature]

            baseline = manifest.get("builtin-baseline", "")
            if len(baseline) > 0:
                baseline_shas.append(baseline)
            
        latest_baseline = self.baselines.get_latest_valid_baseline(baseline_shas)
        bundle_manifest = {
            "name": f"{name}",
            "version": "0.1.0",
            "dependencies": [
                dep.to_vcpkg()
                for dep in sorted(merged_dependencies.values(), key=lambda d: d.name)
            ],
            "features": all_features,
            "builtin-baseline" : latest_baseline,
            "overrides" : [
                override.to_vcpkg()
                for override in sorted(merged_overrides.values(), key=lambda d: d.name)
            ]
        }
        return bundle_manifest, manual_resolves

    def create_merged_vcpkg(self, name: str):
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