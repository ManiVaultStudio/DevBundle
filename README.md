## What is DevBundle - makeproject?

This project allows you create one or more development bundles of HDPS 
repositories to facilitate project development. It clones the repos and 
generates a CMakeLists.txt file that can be used to COnfigure, Generate, Open Project.

If you use the prebuilt binaries the CMake will include all the necessary variables for


## Functionality 

### In current version

* List bundles defined: *makeproject list*
* List a bundle definition: *makeproject list main*
* Make a new bundle from the config *makeproject use main*
* Use an [alternate config file with the `--cfg_file`](#useyourownconfigfile) option
* Use either https (default) or ssh to clone the repo 
* Get prebuilt binaries
* Set CMake variables (as per configuration) in the top-level CMakeLists.txt
* Set debug and release environment paths if using prebuilt binaries
* Protect against accidental deletion of changes to a local repo. Warns:
  ```
  The following repos have local changes or untracked files:
  core
  Resolve these issues manually before running
  ```
* Include a [separate, local, (i.e. not downloaded) directory](#11-using-a-local-development-repo) into the bundle definition 

### Requirements
The project needs two python modules which can be installed with:
```
pip install gitpython
pip install requests
```

### Usage examples

The configuration contains 4 predefined bundles: 
| Bundle name   | Repos                                                                  | Branches              |
| ------------- | ---------------------------------------------------------------------- | --------------------- |
| allmain       | core + all plugins                                                     | main or master        |
| smallmain     | core + CsvLoader, ImageLoaderPlugin, ImageViewerPlugin, t-SNE-Analysis | main or master        |
| branchexample | core + CsvLoader, ImageLoaderPlugin, ImageViewerPlugin, t-SNE-Analysis | feature/serialization |
| smalltest     | core + CsvLoader                                                       | main or master        |

1) List the predefined bundles: 
   ```
   >python makeproject.py list
   allmain
   smallmain
   branchexample
   smalltest
   ```

2) Use the `smalltest` **with https authentication**
   ```
    > python makeproject.py use smalltest
    Cloning from: https://github.com/hdps/core
    ...
    Cloning from: https://github.com/hdps/CsvLoader
    ...
    Downloading QT5152
    Downloaded: D:\Projects\DevBundle\binaries\QT5152.tgz
    Making CMakeLists.txt
    ```

3) Use the `smalltest` **with ssh authentication**

   **Tip**: With SSH on Windows (using Windows Git in a cmd prompt) you can launch an ssh_agent to hold the passphrase thus: 
   ```
   > start-ssh-agent.cmd
   Found ssh-agent at 26736
   Found ssh-agent socket at /tmp/ssh-q1vvuXxLLGyX/agent.1044
   Enter passphrase for /c/Users/<login_name>/.ssh/id_rsa:
   Identity added: /c/Users/<login_name>/.ssh/id_rsa (/c/Users/<login_name>/.ssh/id_rsa)
   Identity added: /c/Users/<login_name>/.ssh/id_ed25519 (<git-id>)
   ```

   ```
   > python makeproject.py use smalltest --ssh
   Cloning from: git@github.com:hdps/core.git
   ...
   Cloning from: git@github.com:hdps/CsvLoader.git
   ...
   Downloading QT5152
   Downloaded: D:\Projects\DevBundle\binaries\QT5152.tgz
   Making CMakeLists.txt
   ```

4) Skip specific binaries 

```
> python makeproject.py use smalltest --skip_binary QT5152
```

In this example the resulting `CMakeLists.txt` will not contain the entries for Qt. You may wish to do this to speed up the install process and if you have a pre-installed version of the binary in question. You will have to manually set the required CMake variables if you do this. To see what the required CMake variables are see the details of the binary your are skipping in the `config.json` file

<div id="useyourownconfigfile"/>

5) Use your own configuration file


To avoid altering the default `config.json` make a copy under another name edit as required  and supply that file name using the `--cfg_file` option. For example if the file is called `my_cfg.json`:

```
python makeproject.py use --cfg_file my_cfg.json my_bundle_name
```


### Understanding the `config.json` file

The `config.json` provided contains a working example of all HDPS plugins (a `build_config`) together with the core on the main branch called `allmaster`. There are in addition a number of other configurations for illustration or testing.

`config.json` contains three major sections: `build_bundles`, `repo_info` and `prebuilt_binaries`. 


#### 1.  `build_bundles`

&nbsp;&nbsp;&nbsp;&nbsp; A `build_bundle` defines a set of HDPS `core` plus plugins to be used in the bundle project. It defines a `name` which should be a meaningful string, a `build_dir` which will contain the `source`, `build` and `install` 
directories and a list of `hdps_repos` used in the bundle project.

&nbsp;&nbsp;&nbsp;&nbsp; `build_dir` will be created relative to the path where the `makeproject.py` script is run.

###### 1.1 Using a local development repo

A `build_bundle` contains a list of `hdps_repos`. Each repo is usually defined using the repo name and branch. However if you have already checked out a repo for development purposes or are creating a new plugin that is not yet in GitHub it may be useful to point to a local path. This can be achieved using the `local` property in the repos configuration. For example if I have MyNewPlugin locally I can include it in a bundle thus: 

```
	"build_bundles": [
		{
			"name": "myplugin_dev",
			"build_dir": "myplugin_dev",
			"hdps_repos": [
				{
					"repo": "core",
					"branch": "feature/qt_6"
				},
				{
					"repo": "MyNewPlugin",
					"branch": "feature/qt_6",
					"local": "D:/Projects/MyNewPlugin"
				}
			]
		},
```


#### 2. `repo_info`

&nbsp;&nbsp;&nbsp;&nbsp;`repo_info` is a central list of all HDPS repos describing subprojects, if any, that are defined in the repo and their project dependencies and binary dependencies. This is essential for creating a top-level CMakeLists.txt with the correct build order dependencies.

&nbsp;&nbsp;&nbsp;&nbsp; This section shall be maintained to reflect the current status of the HDPS projects. (Note: at the moment there is no provision for different dependencies between main and branches - as a workaround a copy of this file can be created.)

&nbsp;&nbsp;&nbsp;&nbsp; These dependencies only need to be listed once for each repo that will be using in the `build_bundles`.

#### 3. `prebuilt_binaries`

&nbsp;&nbsp;&nbsp;&nbsp; Named `<binary_name>` 3rd party binaries available prebuilt in the LKEB Artifactory software repository. These are downloaded and unpacked into the common `binaries` subdirectory. If there is no `--skip_binary <binary_name>`on the command line the associated CMake variables will be defined. The presencene of a `bin_path` causes the path to be appended to the debug/release environments to be able to execute the compiled bundle in one step.

&nbsp;&nbsp;&nbsp;&nbsp; Binaries are downloaded to `<binary_name>.tgz` in the `binaries`common directory and unpacked to a subdirectory with the `<binary_name>`.

&nbsp;&nbsp;&nbsp;&nbsp; `cmake_variables` definitions 
&nbsp;&nbsp;&nbsp;&nbsp; - a variable name ending with `+` will be taken as a list to append to (i.e. generates: `list(APPEND <var> <value>)`).</br>
&nbsp;&nbsp;&nbsp;&nbsp; - a variable name beginning with `+` will be prepended with the path to the binary, directory otherwise provide an absolute path.
### Modes

Accesses using the **--mode** switch. Currently two modes are supported: **clean** (the default) and **cmake_only**. e.g. **python makeproject.py use smalltest --mode cmake_only**

1. **clean**: Remove and reclone all repos
2. **cmake_only**: Leave repos intact onlbuild cmake file 
### Coming soon
* One or more **develop** modes. These will support controlled preservation/overwriting of developer changes on a per repo basis

## Tips for ManiVault building on Linux

### System and installs

Currently the preserred OS is Ubuntu 22.04 or similar.

Install (**sudo apt install**) the following packages:

0. sudo apt-get update
1. sudo apt install libtbb2-dev     (required for pstl support)
2. sudo apt install g++-10

### CMake Config and Generate and Build

Currently the following compiler is supported

1. gcc/g++ version 10

Set the following CMake variables

1. CMAKE_CXX_COMPILER /usr/bin/g++-10
2. CMAKE_C_COMPILER /usr/bin/gcc-10

### Choosing a generator in CMake

Currently only the **Unix makefiles** generator is recommended. Others e.g. **Ninja** may have project dependency issues. This is being worked on (October 2023)   

## Notes

If you don't use the prebuilt binaries for HDPS you will need to manually add one or more of the following definitions (depending on your bundle) in the CMake GUI:

* HDPS_INSTALL_DIR - for HDPS (environment variable)
* QT_DIR - for HDPS (lib/cmake/Qt5)
* Qt5_DIR - for HDPS (lib/cmake/Qt5)
* FREEIMAGE_ROOT_DIR for ImageLoader (directory including lib, bin and include dirs)
* VTK_DIR - for VolumeViewer (lib/cmake/vtk-9.1)
## An example of using the DevBundle - makeproject

Example: main

List the all defined projects. These are some default test projects defined in the )

List the details of main

```shell
 py makeproject.py list main
name: main
build dir: main
hdps_repos:
        repo: https://github.com/hdps/core,     project_name: core      branch: master
        repo: https://github.com/hdps/CsvLoader,        project_name: CsvLoader branch: master
                project: CsvLoader, dependencies: HDPS PointData
        repo: https://github.com/hdps/ImageLoaderPlugin,        project_name: ImageLoaderPlugin branch: master
                project: ImageLoaderPlugin, dependencies: HDPS
        repo: https://github.com/hdps/ImageViewerPlugin,        project_name: ImageViewerPlugin branch: master
                project: ImageViewerPlugin, dependencies: HDPS ImageData
        repo: https://github.com/hdps/t-SNE-Analysis,   project_name: t-SNE-Analysis    branch: master
                project: TsneAnalysisPlugin, dependencies: HDPS ImageData PointData
                project: HsneAnalysisPlugin, dependencies: HDPS ImageData PointData
```






