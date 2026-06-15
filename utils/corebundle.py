"""
 Handle core dependency bundle.

 The core dependency bundle is resolved from files 
 with the name CoreDependConfig.json 
 located in the root repos in the bundle. 
 
 CoreDependConfig.json contains information about 
 additional core extension repos that a plugin requires.
 Typically these are other data plugins

 In the future the core itself may have a list of external
 extension repos.

 This class searches for instances of CoreDependConfig.json
 in the repos retrieved in source. An resolves them into a 
 a list or repos an branch names. These can then be used to retrieve
 the specified versions of the repos. 

 Clashes in definitions will result in errors that must be resolved by the user
"""

from pathlib import Path
from jsonschema import validate
import json
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError, SchemaError
from git import Repo
from typing import List

class CoreBundle:
  BUNDLE_NAME = "CoreDependConfig.json"
  COREBUNDLESCHEMA = Path(Path(__file__).parents[1],'schemas','CoreDependConfig.schema.json')

  def __init__(self, sourceDir: Path):
    schema_data = CoreBundle.COREBUNDLESCHEMA.read_bytes()
    self._schema = json.loads(schema_data)
    self._bundles = []
    self._merged_repos = []
    self._get_selected_corebundles(sourceDir)
    self._merge_core_bundles()


    """Get the selected (based on branchname) core extension repo bundles
    for every core bundle json (CoreDependConfig.json) that was found
    in the source directory. Place then in the self._bundles list
    """
  @property
  def repos(self) -> List[dict]:
    """Get the list of repos and
    the branches corresponding to the 
    resolved CoreDependConfig.json

    Returns:
        List[dict]: repo and branch tuples
    """
    return self._merged_repos
  
  def _get_selected_corebundles(self, sourceDir: Path):
    paths = sorted(sourceDir.glob(f'**/{CoreBundle.BUNDLE_NAME}'))
    # For all the core bundles found validate the json 
    # add the bundle correcponding to the branch name to the
    # list self.__bundles or the default bundle if not matching bundles is found
    for path in paths:
      bundle_json = json.loads(path.read_bytes())
      bundle_repo = Repo(sourceDir)
      branch = bundle_repo.active_branch
      print(f"Get bundle for repo at {str(sourceDir)} on branch: {branch}")
      try:
        Draft202012Validator(self._schema).validate(bundle_json)
      except SchemaError as err:
        print(f"*** Core bundle validation cannot proceed due to schema error ***") 
        print(err)
        raise
      except ValidationError as err:
        print(f"*** Core bundle does not agree with schema***") 
        print(err)
        raise
      bundleNames = [x["name"] for x in bundle_json['bundles']]
      print(f"{len(bundleNames)} Bundles names: {bundleNames} branch: {branch}")
      if str(branch) not in bundleNames:
        branch = "default"
        print(f"Using default core bundle for repo at {path}")
      self._bundles.append([x for x in bundle_json['bundles'] if x["name"] == str(branch)][0])

  def _merge_core_bundles(self):
    for bundle in self._bundles:
      repos = bundle['repos']
      for repo in repos:
        print(f"Repo contents {repo}")
        found = False
        for merged_repo in self._merged_repos:
          if merged_repo['repo'] == repo['repo']:
            if merged_repo['branch'] != repo['branch']:
              raise RuntimeError(f"Branch conflict:  repo: {repo['repo']} with conf branch A: {merged_repo['branch']}, branch B: {repo['branch']}")
        if not found:
          self._merged_repos.append(repo)
