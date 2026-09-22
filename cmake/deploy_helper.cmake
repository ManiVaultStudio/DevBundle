if (APPLE)

    function(add_bundle_schemes)
        cmake_parse_arguments(PARSE_ARGV 0 arg
            "" "BASENAME;CONFIGURATIONS" ""
        )
        # *** DEVELOPER NOTE ***
        # 0000_DevBundleRunner is a proxy for the BUILD_ALL pseudo-target,
        # so running this target ensures that everything is built.
        # Because it is a real target, however, we can set the XCODE properties
        # to get the required launch executable and working directory, something
        # that is not possible on pseude-target ALL_BUILD
        #
        # The name has been chosen so that it appears first in the list of schemes in XCode

        set(DEVBUNDLE_RUNNER_SRC "${CMAKE_CURRENT_BINARY_DIR}/devbundle_runner.cpp")
        message(STATUS "Providing dummy source target in ${DEVBUNDLE_RUNNER_SRC} for ${arg_BASENAME} in ${arg_CONFIGURATIONS}")
        if(NOT EXISTS "${DEVBUNDLE_RUNNER_SRC}")
            file(WRITE "${DEVBUNDLE_RUNNER_SRC}" "int main() { return 0; }\n")
        endif()

        foreach(_config ${arg_CONFIGURATIONS})
            set(MACOS_BUNDLE "${CMAKE_INSTALL_PREFIX}/${_config}")
            set(_dep_name "${arg_BASENAME}_${_config}")
            add_executable("${_dep_name}" "${DEVBUNDLE_RUNNER_SRC}")
            add_dependencies("${_dep_name}" ALL_BUILD)
            set_target_properties("${_dep_name}" PROPERTIES
                EXCLUDE_FROM_ALL ON
                XCODE_GENERATE_SCHEME ON
                XCODE_SCHEME_LAUNCH_CONFIGURATION "${_config}"  
                XCODE_SCHEME_WORKING_DIRECTORY "${MACOS_BUNDLE}/ManiVault Studio.app/Contents/MacOS"
                XCODE_SCHEME_EXECUTABLE "${CMAKE_INSTALL_PREFIX}/${_config}/ManiVault Studio.app/Contents/MacOS/ManiVault Studio"
            )
        endforeach()
    endfunction()

    set_property(GLOBAL PROPERTY MV_PLUGIN_TARGETS "")
    set(MACOS_CODESIGN_IDENTITY - CACHE STRING "Fill your MacOS codesigning identiy here it you have one - otherwise - is used for ad-hoc signing")

    set(MACOS_BUNDLE "${CMAKE_INSTALL_PREFIX}/$<CONFIG>")

    # *** DEVELOPER NOTE ***
    # 0000_DevBundleRunner is a proxy that depends on BUILD_ALL pseudo-target,
    # Running the scheme for  this target ensures that everything is built.
    # Because it is a real target, (BUILD_ALL is a pseudo-target) however, 
    # XCODE properties to get the required launch executable and working directory, 
    # can be set. That is not possible on pseudo-target ALL_BUILD
    #
    # The name has been chosen so that it appears first in the list of schemes in XCode
    #
    # The function adds multiple schemes each with a different build configuration.

    add_bundle_schemes(BASENAME "0000_DevBundleRunner" CONFIGURATIONS "Debug;Release")

    # Override the CMake install function to capture all the Plugin targets in MV_PLUGIN_TARGETS
    # This allows creation of a custom target dependent on the completion of the plugin builds.
    function(install)
        # Once a function <FUNCNAME> is overridden the original is still accessible via _<FUNCNAME>
        # message(STATUS "[install override] called with: ${ARGN}")
        _install(${ARGN})
        # Check for an install(TARGETS...) with LIBRARY DESTINATION Plugins
        # This indicates a plugins target
        if(ARGN)
            list(GET ARGN 0 _first)
            if(_first STREQUAL "TARGETS")
                # message(STATUS "Found targets")
                cmake_parse_arguments(_mv
                    "" ""
                    "TARGETS;EXPORT;LIBRARY;RUNTIME;ARCHIVE;FRAMEWORK;PUBLIC_HEADER"
                    ${ARGN}
                )
                # Capture the LIBRARY argument and check if the DESTINATION sub-argument is PLUGINS
                # Limiting to LIBRARY for MacOS
                foreach(_kind LIBRARY)
                    if(_mv_${_kind})
                        cmake_parse_arguments(_dest "" "DESTINATION" "" ${_mv_${_kind}})
                        #message(STATUS "destination found ${_dest_DESTINATION} with target ${_mv_TARGETS}")
                        if(_dest_DESTINATION MATCHES "(\"\$<CONFIGURATION>/)?Plugins(/\")?")
                            # Add the plugin target name(s) to the global list
                            # message(STATUS "Adding plugins: **${_mv_TARGETS}** to the list")
                            set_property(GLOBAL APPEND PROPERTY MV_PLUGIN_TARGETS ${_mv_TARGETS})
                        endif()
                    endif()
                endforeach()
            endif()
        endif()
    endfunction()

    function(_mv_create_install_fixup)
        # Create 
        # Retrieve the global property containing the Plugin targets
        get_property(_plugin_targets GLOBAL PROPERTY MV_PLUGIN_TARGETS)
        list(REMOVE_DUPLICATES _plugin_targets)
        # It is important that the bothe the plugins and the MV_EXE 
        # targets have completed before triggering this deploy script
        message(STATUS  "Also appending the executable target: MV_Application")
        list(APPEND _plugin_targets "MV_Application")

        # A custom build target (in build_all) is use to define a dependency on list of Plugins
        add_custom_target(AllPluginsInstalled ALL)
        add_dependencies(AllPluginsInstalled ${_plugin_targets})
        message(STATUS "The following plugins have been added to the install step: ${_plugin_targets}")
        message(STATUS "Macdeplotqt exe at ${MACDEPLOYQT_EXECUTABLE}")
        message(STATUS "Extra libdirs for lz4: ${lz4_ROOT}/..")


        if(APPLE)
            get_filename_component(Qt6_LIBPATH "${Qt6_DIR}/../.." ABSOLUTE)
            add_custom_command(TARGET AllPluginsInstalled POST_BUILD
            COMMAND ${CMAKE_COMMAND} 
                -DCMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX}
                -DBUNDLE_DIR=${BUNDLE_DIR}
                -DMACOS_CODESIGN_IDENTITY=${MACOS_CODESIGN_IDENTITY}
                -DCURRENT_CONFIG=$<CONFIG>
                -DPLUGIN_TARGETS="${_plugin_targets}" 
                -DMACDEPLOYQT_EXECUTABLE=${MACDEPLOYQT_EXECUTABLE}
                -DQT6_LIBPATH=${Qt6_LIBPATH}
                -P  "${CMAKE_CURRENT_LIST_DIR}/cmake/macdeploy_main.cmake"
            COMMENT "Running post-install Apple fixup, code-signing")
        endif()
    endfunction()

    # The setup of the install fixup target occurs after everything else has 
    # been configured (CMake configure stage).
    # All the plugins have been identified in the install function override
    cmake_language(DEFER CALL _mv_create_install_fixup)
endif()
