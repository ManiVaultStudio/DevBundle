function(prebundle_cleanup)
    file(GLOB BUNDLE_FRAMEWORKS "${MACOS_BUNDLE_FRAMEWORKS}/*")
    if(BUNDLE_FRAMEWORKS)
        message(STATUS "Sanitize ${MACOS_BUNDLE_FRAMEWORKS}")
        foreach(FRAMEWORK ${BUNDLE_FRAMEWORKS})
            if(IS_DIRECTORY ${FRAMEWORK} AND FRAMEWORK MATCHES "Qt")
                message(STATUS "The following Qt frameworks are in the MacOS app bundle:")
                message(STATUS "  ${FRAMEWORK}")
                message(STATUS "Removing all Qt frameworks from the MacOS app bundle (we add them later again in the Mac deploy Qt step)")
                file(REMOVE_RECURSE ${FRAMEWORK})
            else()
                message(STATUS "Also found ${FRAMEWORK}")
            endif()
        endforeach()

        message(STATUS "Verifying that the Qt frameworks were successfully removed...")
        file(GLOB REMAINING_FRAMEWORKS "${MACOS_BUNDLE_FRAMEWORKS}/*")
        if(REMAINING_FRAMEWORKS)
            message(STATUS "There are files present in: ${MACOS_BUNDLE_FRAMEWORKS} namely: ${REMAINING_FRAMEWORKS}")
        else()
            message(STATUS "All Qt frameworks have been removed from: ${MACOS_BUNDLE_FRAMEWORKS}")
        endif()
    endif()
    file(REMOVE_RECURSE "${MACOS_PLUGIN_DEPENDENCIES}")
endfunction()

#### ????? Necessary ???????
function(set_appbundle_executable)
	message(STATUS "Make ManiVault Studio application executable")
	execute_process(COMMAND chmod +x "${MACOS_BUNDLE_EXECUTABLE}"
		WORKING_DIRECTORY "${CMAKE_INSTALL_PREFIX}/${CURRENT_CONFIG}"
		RESULT_VARIABLE _chmod_result
		OUTPUT_VARIABLE _chmod_out
		ERROR_VARIABLE _chmod_out
	)
	if(NOT _chmod_result EQUAL 0)
	    message(FATAL_ERROR "Make executable failed with: ${_chmod_out}")
	else()
		message(STATUS "Make executable succeeded.")
	endif()
endfunction()

function(remove_bundle_plugins)
    if(EXISTS ${MACOS_BUNDLE_PLUGINS})
        file(GLOB OLD_PLUGINS "${MACOS_BUNDLE_PLUGINS}/*")
        if(OLD_PLUGINS)
            message(STATUS "Remove old ${MACOS_BUNDLE_PLUGINS}")
            foreach(PLUGIN ${OLD_PLUGINS})
                if(IS_DIRECTORY ${PLUGIN} AND PLUGIN MATCHES "Qt")
                    message(STATUS "The following plugins are in the MacOS app bundle:")
                    message(STATUS "  ${PLUGIN}")
                    message(STATUS "Removing all plugins from the MacOS app bundle (we add them later again in the Mac deploy Qt step)")
                    file(REMOVE_RECURSE ${PLUGIN})
                endif()
            endforeach()

            message(STATUS "Verifying that all plugins were successfully removed...")
            file(GLOB REMAINING_FRAMEWORKS "${MACOS_BUNDLE_PLUGINS}/*")
            if(REMAINING_FRAMEWORKS)
                message(STATUS "There are still plugins present in: ${MACOS_BUNDLE_PLUGINS}")
            else()
                message(STATUS "All plugins have been removed from: ${MACOS_BUNDLE_PLUGINS}")
            endif()
        endif(OLD_PLUGINS)
    else()
        message(STATUS "No plugins directory ${MACOS_BUNDLE_PLUGINS} found to clean")
    endif()
endfunction()


function(fix_plugin_dependencies)
    # Intra plugin dependencies should all be expressed using the @loader_path
    # syntax to prevent macdeployqt moving them into Frameworks
    file(GLOB _plugin_files "${MACOS_BUNDLE}/Plugins/*.dylib")

    foreach(_target_plugin ${_plugin_files})
        foreach(_sibling_plugin ${_plugin_files})
            get_filename_component(_sibling_name "${_sibling_plugin}" NAME)

            if(NOT "${_target_plugin}" STREQUAL "${_sibling_plugin}")
                execute_process(
                    COMMAND "install_name_tool"
                            -change "@rpath/${_sibling_name}" "@loader_path/${_sibling_name}"
                            "${_target_plugin}"
                    OUTPUT_QUIET
                    ERROR_QUIET
                )
                # No RESULT_VARIABLE check — a nonzero exit here just means
                # _target_plugin doesn't depend on _sibling_name, which is
                # the expected/common case, not an error.
            endif()
        endforeach()
    endforeach()

    # After the fix intra-plugin dependencies for all Plugins
    #  shows paths for debugging purposes
    # message(STATUS "Post plugin deps rpaths:")
    # execute_process(COMMAND zsh -c "ls *.dylib | xargs -t -I % otool -l % | grep -i -A2 path"
    #     WORKING_DIRECTORY "${MACOS_BUNDLE}/Plugins"
    #     RESULT_VARIABLE _rpath_result
	# 	OUTPUT_VARIABLE _rpath_out
	# 	ERROR_VARIABLE _rpath_out
    # )
    # if(NOT _rpath_result EQUAL 0)
	#     message(FATAL_ERROR "rpath check failed with: ${_rpath_out}")
	# else()
	# 	message(STATUS "rpath check succeeded with ${_rpath_out}")
	# endif()
endfunction()

function(macdeployqt_bundle)
    # 1) deploy just the bundle .app & record the contents of Contents/Frameworks
    # 2) deploy the bundle.app + the -executable for all plugins & record the cotents of Contents/Frameworks
    # 3) the additional (non-QT) dependencies added in step 2) are moved to PluginDependencies

    # Debug info
    message(STATUS "Show bundle contents beforrunning macdeployqt")
    message(STATUS  "Contents of ${MACOS_BUNDLE_APP}")
    execute_process(COMMAND ls -al "${MACOS_BUNDLE_APP}")
    message(STATUS  "Contents of ${MACOS_BUNDLE_EXEDIR}")
    execute_process(COMMAND ls -al "${MACOS_BUNDLE_EXEDIR}")
    message(STATUS  "Contents of ${MACOS_BUNDLE_PLUGINS}")
    execute_process(COMMAND ls -al "${MACOS_BUNDLE_PLUGINS}")
    message(STATUS  "Contents of ${MACOS_BUNDLE_FRAMEWORKS}")
    execute_process(COMMAND ls -al "${MACOS_BUNDLE_FRAMEWORKS}")
    # /Debug info

    # First deploy the app only.
    # This has already been done in the core/ManiVault/CMakeLists.txt - so no need to repeat the step here
    # Record appl-only associated dylib dependencies in the Frameworks
    file(GLOB APP_ONLY_DEPENDENCIES "${MACOS_BUNDLE_FRAMEWORKS}/*.dylib")
    message(STATUS "The ManiVault Studio app has dependencies ${APP_ONLY_DEPENDENCIES} apart from Qt")

    set(_extra_exec_args "")
    file(GLOB DEPLOYED_PLUGINS "${MACOS_BUNDLE}/Plugins/*")
    message(STATUS "These plugins are deployed ${DEPLOYED_PLUGINS}")
    foreach(_plugin_target ${DEPLOYED_PLUGINS})
        message(STATUS  "Adding ${_plugin_target} to executable list")
        list(APPEND _extra_exec_args  "-executable=${_plugin_target}" )
    endforeach()
    list(JOIN _extra_exec_args " " _str_exec_args)
    message(STATUS  "Additionally deploying plugins: ${_str_exec_args}")
    execute_process(COMMAND launchctl asuser $ENV{UID} "${MAC_DEPLOY_QT_EXE}" "${MACOS_BUNDLE_APP}" ${_extra_exec_args} # "-verbose=3"  
    	WORKING_DIRECTORY "${CMAKE_INSTALL_PREFIX}/${CURRENT_CONFIG}"
		RESULT_VARIABLE _mqt_result
		OUTPUT_VARIABLE _mqt_out
		ERROR_VARIABLE _mqt_out
    )

	if(NOT _mqt_result EQUAL 0)
	    message(FATAL_ERROR "Macdeployqt of bundle + plugins failed with: ${_mqt_out}")
	else()
		message(STATUS "Macdeployqt of bundle + plugins succeeded with ${_mqt_out}")
	endif()
        # Record associated dylib dependencies in the Frameworks
    file(GLOB APP_AND_PLUGIN_DEPENDENCIES "${MACOS_BUNDLE_FRAMEWORKS}/*.dylib")
    message(STATUS "The ManiVault Studio app + plugins has dependencies ${APP_AND_PLUGIN_DEPENDENCIES} apart from Qt")

    foreach(_dependency_ ${APP_ONLY_DEPENDENCIES})
        list(REMOVE_ITEM APP_AND_PLUGIN_DEPENDENCIES ${_dependency_})
    endforeach()
    message(STATUS "Plugin only dependencies ${APP_AND_PLUGIN_DEPENDENCIES} apart from Qt")
    if(NOT EXISTS "${MACOS_PLUGIN_DEPENDENCIES}")
        file(MAKE_DIRECTORY "${MACOS_PLUGIN_DEPENDENCIES}")
    endif()
    foreach(_dependency_ ${APP_AND_PLUGIN_DEPENDENCIES})
        get_filename_component(full_dep_name "${_dependency_}" NAME)
        message(STATUS  "Moving dependency ${full_dep_name}")
        file(RENAME ${_dependency_} "${MACOS_PLUGIN_DEPENDENCIES}/${full_dep_name}")
    endforeach()

    # The dependencies have been moved but the plugins still reference 
    # them via @loader_path/../${MACOS_BUNDLE_FRAMEWORKS}
    # For each dependency perform an install_name_tool -change old new on each plugin
    file(RELATIVE_PATH _rel_plugin_framework_path_ "${MACOS_BUNDLE}/Plugins" "${MACOS_BUNDLE_FRAMEWORKS}")
    foreach(_dependency_ ${APP_AND_PLUGIN_DEPENDENCIES})
        get_filename_component(full_dep_name "${_dependency_}" NAME)
        set(_name_change_command "-change @loader_path/${_rel_plugin_framework_path_}/${full_dep_name} @rpath/${full_dep_name}")
        message(STATUS "Dependency location fixup: ${_name_change_command}")
        foreach(_plugin_target ${DEPLOYED_PLUGINS})
            execute_process(COMMAND "install_name_tool" 
                -change "@loader_path/${_rel_plugin_framework_path_}/${full_dep_name}" "@rpath/${full_dep_name}"
                "${_plugin_target}"
                ERROR_QUIET
                RESULT_VARIABLE _int_result
                OUTPUT_VARIABLE _int_out
                ERROR_VARIABLE _int_out
            )

            if(NOT _int_result EQUAL 0)
                message(FATAL_ERROR "install_name_tool failed with: ${_int_out} target ${_plugin_target}")
            else()
                message(STATUS "install_name_tool succeeded with ${_int_out} target ${_plugin_target}")
            endif()
            
        endforeach()
    endforeach()

endfunction()

function(add_plugin_dependencies_rpath)
    file(GLOB DEPLOYED_PLUGINS "${MACOS_BUNDLE}/Plugins/*")
    message(STATUS "These plugins are deployed ${DEPLOYED_PLUGINS}")
    foreach(_plugin_target ${DEPLOYED_PLUGINS})
        message(STATUS  "Adding PluginDependencies rpath to ${_plugin_target}")
        execute_process(
            COMMAND "install_name_tool"
                -add_rpath "@loader_path/../PluginDependencies"
                "${_plugin_target}"
            OUTPUT_QUIET
            ERROR_QUIET
        )                    
    endforeach()  
endfunction()

function(remove_binary_qt_rpath)
    message(STATUS  "Remove redundant rpath in ${MACOS_BUNDLE_EXECUTABLE}")
    execute_process(
        COMMAND "install_name_tool" 
            -delete_rpath "\"${QT6_LIBPATH}\"" 
            "${MACOS_BUNDLE_EXECUTABLE}"
            OUTPUT_QUIET
            ERROR_QUIET
    )
    file(GLOB REMAINING_DEPENDENCIES "${MACOS_BUNDLE_FRAMEWORKS}/*.dylib")
    foreach(_dependency_ ${REMAINING_DEPENDENCIES})
        message(STATUS  "Adding PluginDependencies rpath to ${_plugin_target}")
        execute_process(
            COMMAND "install_name_tool"
                -delete_rpath "\"${QT6_LIBPATH}\"" 
                "${_dependency_}"
            OUTPUT_QUIET
            ERROR_QUIET
        )                    
    endforeach()  
endfunction()