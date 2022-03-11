## What is DevBundle - makeproject

This project allows you create one or more development bundles of HDPS 
repositories to facilitate project development.

## Functionality 

### In current version

* List bundles defined: *makeproject list*
* List a bundle definition: *makeproject list main*
* Make a new bundle from the config *makeproject use main*

### Coming soon
* Support for overwriting and existing directory (recommend that each bundle is in a separate dir in this release)
* Support for CMake defines.

## Notes

For HDPS you will need to manually add one or more of the following definitions (depending on your bundle) in the CMake GUI:

* HDPS_INSTALL_DIR (environment variable)
* QT_DIR (lib/cmake/Qt5)
* Qt5_DIR (lib/cmake/Qt5)
* FREEIMAGE_ROOT_DIR (directory including lib, bin and include dirs)
## An example of using the DevBundle - makeproject

Example: main

List the all defined projects. These are some default test projects defined in the )

```shell
> py makeproject.py list
test1
test2
main
serial
```

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

Make the bundle

```shell
> py makeproject.py use main
Cloning from: https://github.com/hdps/core
remote: Counting objects: 100% (4908/4908), done.

remote: Compressing objects: 100% (2909/2909), done.

Receiving objects: 100% (14299/14299), 32.57 MiB | 2.96 MiB/s, done.

Resolving deltas: 100% (9978/9978), done.

remote: Counting objects: 100% (277/277), done.

remote: Compressing objects: 100% (123/123), done.

Receiving objects: 100% (6330/6330), 13.82 MiB | 3.05 MiB/s, done.

Resolving deltas: 100% (4581/4581), done.

remote: Counting objects: 100% (488/488), done.

remote: Compressing objects: 100% (192/192), done.

Receiving objects: 100% (3641/3641), 1.55 MiB | 3.04 MiB/s, done.

Resolving deltas: 100% (2562/2562), done.

Receiving objects: 100% (183/183), 45.51 KiB | 1.98 MiB/s, done.

Resolving deltas: 100% (119/119), done.

Cloning from: https://github.com/hdps/CsvLoader
remote: Counting objects: 100% (79/79), done.

remote: Compressing objects: 100% (48/48), done.

Receiving objects: 100% (79/79), 17.13 KiB | 3.43 MiB/s, done.

Resolving deltas: 100% (36/36), done.

Cloning from: https://github.com/hdps/ImageLoaderPlugin
remote: Counting objects: 100% (495/495), done.

remote: Compressing objects: 100% (192/192), done.

Receiving objects: 100% (3686/3686), 9.36 MiB | 2.13 MiB/s, done.

Resolving deltas: 100% (2897/2897), done.

Cloning from: https://github.com/hdps/ImageViewerPlugin
remote: Counting objects: 100% (618/618), done.

remote: Compressing objects: 100% (417/417), done.

Receiving objects: 100% (6506/6506), 1.63 MiB | 2.77 MiB/s, done.

Resolving deltas: 100% (5328/5328), done.

Cloning from: https://github.com/hdps/t-SNE-Analysis
remote: Counting objects: 100% (1985/1985), done.

remote: Compressing objects: 100% (1224/1224), done.

Receiving objects: 100% (2733/2733), 71.08 MiB | 3.11 MiB/s, done.

Resolving deltas: 100% (1817/1817), done.

Making CMakeLists.txt
```

At this point the subdirectory (in this case called main) will contain all the 
cloned repos at the desired branch and a top-level CMakeLists.txt.







