# DevBundle Deploy Helper for DevBundle

This documents the __deploy_helper.cmake__ and ancillary files. 

## Goals

The deployment servs two goals:

### 1. Support development in a simulated end-user environment

The __ManiVault Studio__ application core and plugins include a post-build custom step that places the result of the build into an __install__ directory. This is intended to simulate the install environment by an install on a user's machine for a developer.

However for some platforms an extra deploy steps are required achieve a more accurate setup. The __DevBundle Deploy Helper__ addresses this initially with the focus on MacOS. 

### 2. Function as a CI install builder

A secondary goal of the __DevBundle Deploy Helper__ is to provide an all-in-one build and deploy that can be used during the creation of distributables in the CI. Further details are T.B.D.

## MacOS deployment functionality

To understand the steps involved in ManiVault Studio deployment consider first the install structure shown below

### Install structure
On MacOS we require the following deployment structure 

``` 
├── Customization
├── ManiVault Studio.app <The MacOS app bundle>
│   └── Contents
│       ├── Frameworks
│       │   ├── <Multiple non-commercial license Qt*.frameworks including QtWebEngine>
│       │   ├── <ManiVault Studio app specific dependencies>
│       ├── Info.plist
│       ├── MacOS
│       │   └── ManiVault Studio
│       ├── PkgInfo
│       ├── PlugIns
│       └── Resources
├── PluginDependencies
│   ├── <Plugin specific dependencies>
├── Plugins
│   ├── <All ManiVault Studio Plugins for the distribution>
├── examples
│   └── workspaces <Workspace layout files>
├── include
│   └── <Include files for 3-party development>   
├── lib
│   └── libMV_Public.dylib <The ManiVault Studio public core API)>
└── license
    └── <All license files>
``` 

### Operations

To create this structure the Deploy Helper performs or assumes several steps as listed below. Note, the list is an architectural description of how the problem is solved rather than a one-to-one description of the actual CMake code. The logic is based on the ManiVault Studio/Install repo.

#### a) Cleanup

Perform general cleanup from previous builds.

#### b) Macdeployqt for ManiVault Studio core

__This step is not run by Deploy Helper but included here for completeness__: The macdeployqt tool is run by the __ManiVault Studio core__ build step. This creates the MacOS app bundle containing the executable, this includes all Qt and other _.dylib dependencies_ in __Contents/Frameworks__. 

#### c) Identification of ManiVault Studio core dependencies

The previous strb b) places a number of core specific _dylib dependencies_ in the __Contents/Frameworks__ bundle diectory. A list of these _dylib dependencies_ is retained in this step.

#### d) Intra-plugin dependency setting

Each Plugin with a dependency on another Plugin will have that dependency path changed to an __@loader_path/&lt;DependentPlugin&gt;__ style path because they are siblings in the __Plugis__ directory. This also prevents __macdeployqt__ from copying __Plugins__ in the __Contents/Frameworks__ directory. 

#### e) Macdeployqt for ManiVault Studio Plugins

Run __macdeployqt__ on the core bundle including each Plugin (using the --executable parameter) in the __Plugins__ directory. Note the new list of _dylib dependencies_ in the __Contents/Frameworks__ directory.

#### f) Plugins Specific Dependency installation

The extra dylib dependencies found in Step e), compared with Step c), are Plugin related Dependencies and are moved to the __PluginDependencies__ directory. All depending Plugins have ther dependency path changed to @rpath/<dylib-dependency> and an LC_RPATH of the type __@loader_path/../PluginDependencies__ ensures that they will be located.


#### g) Signing
The __ManiVault Studio.app__, all the __Plugins__ and the __QtWebEngineProcess__ (found in the __Contents/Frameworks__ section of the bundle) must all be signed. Signing should take place with either 

1.) An Apple issued Developer Certificate 
2.) A Self-Signed local certificate. 

The latter can be created in the Keychain App on MacOS and is suitable for development testing.

The following three items are signed:

1.) The QtWebEngine
2.) All the Plugins
3.) The ManiVault Studio.app bundle

Signing is performed using the key give in the __MACOS_CODESIGN_IDENTITY__ CMake variable that can be completed in the CMake GUI.



