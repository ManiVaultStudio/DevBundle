#!/usr/bin/env python3
"""
merge_vcpkg_manifest.py - merge several vcpkg.json manifests into one "common" manifest.

Usage:
    python3 merge_vcpkg_manifest.py [--vcpkg-repo /path/to/vcpkg] <manifest1.json> <manifest2.json> ...

    --vcpkg-repo is optional. If omitted (or the path doesn't exist), the
    vcpkg repo is cloned to a temp directory automatically and cleaned up
    when the script exits. Requires GitPython (`pip install GitPython`).

What it does:
    1. Unions all "dependencies" entries (by package name), merging feature
       lists and reconciling "platform" constraints.
    2. Unions all "overrides" entries (by package name). If two input files
       pin different versions of the same package, prints a WARNING and
       keeps the newest one.
    3. Sets "builtin-baseline" to whichever input baseline commit is newest,
       determined by asking the local vcpkg git repo for each commit's date.
    4. Writes the merged manifest as name="common", version="0.0.1" (both
       overridable via flags).
"""

import argparse
import atexit
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from git import Repo
from git.exc import GitCommandError


# --------------------------------------------------------------------------
# vcpkg-style version comparison
# --------------------------------------------------------------------------
# vcpkg versions look like "1.10.0", "2019-04-07", "3.1.4.1", optionally
# followed by "#<port-version>". We compare the "#port-version" suffix
# numerically, and compare the base version by tokenizing into runs of
# digits / non-digits (this naturally handles both dotted-numeric schemes
# and ISO date schemes without needing to know which scheme a given port
# uses).

def _parse_version(v):
    base, _, port = v.partition("#")
    port_version = int(port) if port else 0
    return base, port_version


def _tokenize(base):
    return [int(tok) if tok.isdigit() else tok
            for tok in re.findall(r"\d+|[^\d]+", base)]


def compare_versions(v1, v2):
    """Return -1, 0, or 1 comparing vcpkg version strings v1 and v2."""
    b1, p1 = _parse_version(v1)
    b2, p2 = _parse_version(v2)
    t1, t2 = _tokenize(b1), _tokenize(b2)
    for x, y in zip(t1, t2):
        if type(x) is not type(y):
            x, y = str(x), str(y)
        if x != y:
            return -1 if x < y else 1
    if len(t1) != len(t2):
        return -1 if len(t1) < len(t2) else 1
    if p1 != p2:
        return -1 if p1 < p2 else 1
    return 0


def newest_version(versions):
    best = versions[0]
    for v in versions[1:]:
        if compare_versions(v, best) > 0:
            best = v
    return best


# --------------------------------------------------------------------------
# vcpkg repo resolution: reuse a local clone, or clone one on the fly
# --------------------------------------------------------------------------

VCPKG_REPO_URL = "https://github.com/microsoft/vcpkg.git"


class VcpkgRepoResolver:
    """Resolves a usable local vcpkg git repo, cloning one to a temp
    directory if the caller didn't supply an existing path. Mirrors the
    clone-or-update pattern used elsewhere in our tooling."""

    def __init__(self, vcpkg_repo_url: str = VCPKG_REPO_URL):
        self.vcpkg_repo_url = vcpkg_repo_url
        self.repo: Optional[Repo] = None
        self.vcpkg_repo_path: Optional[Path] = None
        self.temp_dir: Optional[Path] = None

    def clone_or_update_repo(self, local_path: Optional[str] = None) -> Path:
        """Use an existing vcpkg repo if given, else clone one. Returns the
        resulting repo path."""
        if local_path and Path(local_path).exists():
            print(f"Using existing vcpkg repository at: {local_path}", file=sys.stderr)
            self.vcpkg_repo_path = Path(local_path)
            self.repo = Repo(self.vcpkg_repo_path)
            
        else:
            # No local path supplied: clone one to a temp directory that we
            # clean up on exit. We deliberately do NOT use a shallow
            # (depth=1) clone here, because we need to be able to resolve
            # whatever builtin-baseline commits appear in the input
            # manifests, which are usually *not* the current tip of the
            # repo. Instead we do a shallow clone up front for speed, and
            # fetch any specific missing commit on demand (GitHub supports
            # fetching a commit directly by its SHA).
            self.temp_dir = Path(tempfile.mkdtemp(prefix="vcpkg-merge-"))
            self.vcpkg_repo_path = self.temp_dir / "vcpkg"
            print(f"Cloning vcpkg repository to: {self.vcpkg_repo_path}", file=sys.stderr)
            print("This may take a few minutes...", file=sys.stderr)

            try:
                self.repo = Repo.clone_from(
                    self.vcpkg_repo_url,
                    self.vcpkg_repo_path,
                    depth=1,
                )
                print("Repository cloned successfully.", file=sys.stderr)
            except Exception as e:
                print(f"Error cloning repository: {e}", file=sys.stderr)
                raise

            atexit.register(self._cleanup)

        return self.vcpkg_repo_path

    def _cleanup(self):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def ensure_commit(self, commit_hash: str) -> bool:
        """Make sure commit_hash is present locally, fetching it on demand
        (needed after a shallow clone). Returns True if the commit is
        available afterward."""
        try:
            self.repo.commit(commit_hash)
            return True
        except (ValueError, Exception):
            pass
        try:
            self.repo.git.fetch("--depth", "1", "origin", commit_hash)
            self.repo.commit(commit_hash)
            return True
        except (GitCommandError, ValueError, Exception):
            return False


# --------------------------------------------------------------------------
# builtin-baseline resolution via the local vcpkg git repo
# --------------------------------------------------------------------------

def commit_timestamp(resolver: VcpkgRepoResolver, commit_hash):
    """Return (unix_timestamp, commit_datetime) for commit_hash, or
    (None, None) if it can't be resolved in the given repo."""
    if not resolver.ensure_commit(commit_hash):
        return None, None
    try:
        commit = resolver.repo.commit(commit_hash)
        return commit.committed_date, commit.committed_datetime
    except Exception:
        return None, None
 
 
def newest_baseline(resolver: VcpkgRepoResolver, baselines):
    """baselines: list of (commit_hash, source_file). Returns the newest
    commit hash, warning about any that couldn't be resolved."""
    dated = []
    for commit, source in baselines:
        ts, dt = commit_timestamp(resolver, commit)
        if ts is None:
            print(f"WARNING: could not resolve builtin-baseline '{commit}' "
                  f"(from {source}) in vcpkg repo '{resolver.vcpkg_repo_path}'; "
                  f"ignoring it when picking the newest baseline.", file=sys.stderr)
        else:
            dated.append((ts, commit, source, dt))
 
    if not dated:
        print("WARNING: none of the input builtin-baseline commits could be "
              "resolved; falling back to the first manifest's baseline.",
              file=sys.stderr)
        return baselines[0][0]

    dated.sort(key=lambda t: t[0])
    newest_ts, newest_commit, newest_source, newest_dt = dated[-1]
 
    distinct = {c for _, c, _, _ in dated}
    if len(distinct) > 1:
        print("NOTE: input manifests use different builtin-baseline commits:",
              file=sys.stderr)
        for ts, commit, source, dt in dated:
            print(f"    {commit}  {dt.strftime('%Y-%m-%d %H:%M:%S %z')}  ({source})",
                  file=sys.stderr)
        print(f"  -> using newest: {newest_commit}  "
              f"{newest_dt.strftime('%Y-%m-%d %H:%M:%S %z')}  (from {newest_source})",
              file=sys.stderr)

    return newest_commit


# --------------------------------------------------------------------------
# dependency merging
# --------------------------------------------------------------------------

def dep_name(dep):
    return dep if isinstance(dep, str) else dep["name"]


def merge_features(all_features_with_source):
    """
    all_features_with_source:
        list of (feature_name, feature_definition, source_file)

    Returns merged features dictionary.
    """
    by_name = {}

    for name, feature, source in all_features_with_source:
        by_name.setdefault(name, []).append((feature, source))

    merged = {}

    for name in sorted(by_name):
        entries = by_name[name]

        descriptions = {
            f.get("description")
            for f, _ in entries
            if "description" in f
        }

        if len(descriptions) > 1:
            print(
                f"WARNING: feature '{name}' has different descriptions "
                f"across input manifests; using the first.",
                file=sys.stderr,
            )

        description = next(iter(descriptions), None)

        deps = []
        for f, source in entries:
            for dep in f.get("dependencies", []):
                deps.append((dep, source))

            # Copy any feature fields we don't explicitly merge
            for k, v in f.items():
                if k not in ("description", "dependencies"):
                    merged_feature[k] = v

        merged_feature = {}

        if description:
            merged_feature["description"] = description

        if deps:
            merged_feature["dependencies"] = merge_dependencies(deps)

        merged[name] = merged_feature

    return merged


def merge_dependencies(all_deps_with_source):
    """all_deps_with_source: list of (dep_entry, source_file).
    Returns a sorted list of merged dependency entries."""
    by_name = {}  # name -> list of (entry, source)
    for dep, source in all_deps_with_source:
        by_name.setdefault(dep_name(dep), []).append((dep, source))

    merged = []
    for name in sorted(by_name):
        entries = by_name[name]

        # If every occurrence is the plain string form, dependency has no
        # extra constraints -> keep it simple.
        if all(isinstance(e, str) for e, _ in entries):
            merged.append(name)
            continue

        # Otherwise merge features (union) and reconcile "platform".
        features = set()
        host = False
        platforms = set()
        extra_fields = {}
        for e, source in entries:
            if isinstance(e, str):
                continue
            for feat in e.get("features", []):
                features.add(feat)
            if e.get("host"):
                host = True
            if "platform" in e:
                platforms.add(e["platform"])
            for k, v in e.items():
                if k in ("name", "features", "host", "platform"):
                    continue
                extra_fields[k] = v  # last one wins for rare fields

        if len(platforms) > 1:
            print(f"WARNING: dependency '{name}' has conflicting 'platform' "
                  f"constraints across input manifests ({sorted(platforms)}); "
                  f"dropping the platform restriction so it's available "
                  f"everywhere it's needed.", file=sys.stderr)
            platform = None
        elif len(platforms) == 1:
            plat = next(iter(platforms))
            # If some occurrences of this dep had NO platform restriction at
            # all (either the plain-string form, or a dict without a
            # "platform" key), that manifest needs it unconditionally, so
            # the restriction can't be kept either.
            unrestricted = any(
                isinstance(e, str) or "platform" not in e
                for e, _ in entries
            )
            if unrestricted:
                print(f"WARNING: dependency '{name}' is restricted to "
                      f"platform '{plat}' in some manifests but required "
                      f"unconditionally in others; dropping the platform "
                      f"restriction.", file=sys.stderr)
                platform = None
            else:
                platform = plat
        else:
            platform = None

        if not features and not host and not platform and not extra_fields:
            merged.append(name)
            continue

        entry = {"name": name}
        if features:
            entry["features"] = sorted(features)
        if host:
            entry["host"] = True
        if platform:
            entry["platform"] = platform
        entry.update(extra_fields)
        merged.append(entry)

    return merged


# --------------------------------------------------------------------------
# override merging
# --------------------------------------------------------------------------

def merge_overrides(all_overrides_with_source):
    by_name = {}  # name -> list of (version, source)
    for ov, source in all_overrides_with_source:
        by_name.setdefault(ov["name"], []).append((ov["version"], source))

    merged = []
    for name in sorted(by_name):
        versions = by_name[name]
        distinct = {v for v, _ in versions}
        if len(distinct) > 1:
            print(f"WARNING: dependency '{name}' is pinned to different "
                  f"versions across input manifests:", file=sys.stderr)
            for v, source in versions:
                print(f"    {v}  ({source})", file=sys.stderr)
            best = newest_version(list(distinct))
            print(f"  -> using newest: {best}", file=sys.stderr)
        else:
            best = next(iter(distinct))
        merged.append({"name": name, "version": best})

    return merged


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifests", nargs="+", type=Path,
                     help="Paths to input vcpkg.json manifest files")
    ap.add_argument("--vcpkg-repo", type=Path, default=None,
                     help="Path to a local clone of the vcpkg repo, used to "
                          "compare builtin-baseline commits. Optional: if "
                          "omitted (or the path doesn't exist), a temporary "
                          "clone is made automatically and removed on exit.")
    ap.add_argument("--name", default="common")
    ap.add_argument("--version", default="0.0.1")
    ap.add_argument("-o", "--output", type=Path, default=Path("vcpkg.json"))
    args = ap.parse_args()

    all_deps = []
    all_overrides = []
    all_features = []
    baselines = []

    for path in args.manifests:
        data = json.loads(path.read_text())
        src = path.name

        for dep in data.get("dependencies", []):
            all_deps.append((dep, src))

        for feat_name, feat_def in data.get("features", {}).items():
            all_features.append((feat_name, feat_def, src))

        for ov in data.get("overrides", []):
            all_overrides.append((ov, src))

        bl = data.get("builtin-baseline")
        if bl:
            baselines.append((bl, src))

    merged_deps = merge_dependencies(all_deps)
    merged_overrides = merge_overrides(all_overrides)
    merged_features = merge_features(all_features)

    result = {
        "name": args.name,
        "version": args.version,
        "dependencies": merged_deps,
    }

    if merged_features:
        result["features"] = merged_features

    if baselines:
        resolver = VcpkgRepoResolver()
        resolver.clone_or_update_repo(args.vcpkg_repo)
        result["builtin-baseline"] = newest_baseline(resolver, baselines)

    if merged_overrides:
        result["overrides"] = merged_overrides

    args.output.write_text(json.dumps(result, indent=4) + "\n")
    print(f"\nWrote merged manifest to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
