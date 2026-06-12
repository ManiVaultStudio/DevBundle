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

class CoreBundle:
  BUNDLE_NAME = "CoreDependConfig.json"
  COREBUNDLESCHEMA = f"{Path(__file__).parents[1] + 'schemas' + 'CoreDependConfig.schema.json'}"

  def __init__(self, sourceDir: Path):
    pass

  def _resolve_corebundles(self, sourceDir: Path):
    paths = sorted(sourceDir.glob(f'**/{CoreBundle.BUNDLE_NAME}'))
    


  @property
  def repos(self) -> List[tuple]:
    """Get the list of repos and
    the branches corresponding to the 
    resolved CoreDependConfig.json

    Returns:
        List[tuple]: repo and branch tuples
    """