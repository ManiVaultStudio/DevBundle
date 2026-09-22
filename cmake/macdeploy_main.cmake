# Deploy bundle
separate_arguments(PLUGIN_TARGETS)
message(STATUS "${PLUGIN_TARGETS} installed to: ${CMAKE_INSTALL_PREFIX}/${CURRENT_CONFIG}/Plugins extra libdirs for deploy ${MACDEPLOYQT_LIBDIRS}")


set(MACOS_BUNDLE "${CMAKE_INSTALL_PREFIX}/${CURRENT_CONFIG}")
set(MACOS_PLUGIN_DEPENDENCIES  "${CMAKE_INSTALL_PREFIX}/${CURRENT_CONFIG}/PluginDependencies")
set(MAC_DEPLOY_QT_EXE ${MACDEPLOYQT_EXECUTABLE})

set(MACOS_BUNDLE_APP "${MACOS_BUNDLE}/ManiVault Studio.app")          # Location of the MacOS .app
set(MACOS_BUNDLE_EXEDIR "${MACOS_BUNDLE_APP}/Contents/MacOS")          # Location of the executable)
set(MACOS_BUNDLE_EXECUTABLE "${MACOS_BUNDLE_APP}/Contents/MacOS/ManiVault Studio") # Startup executable
set(MACOS_BUNDLE_WEBENGINE "${MACOS_BUNDLE_APP}/Contents/Frameworks/QtWebEngineCore.framework/Helpers/QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess") # The Webengine

set(MACOS_BUNDLE_CONTENTS "${MACOS_BUNDLE_APP}/Contents")             # Location of the MacOS .app contents
set(MACOS_BUNDLE_FRAMEWORKS "${MACOS_BUNDLE_CONTENTS}/Frameworks")    # Location of the MacOS .app frameworks
set(MACOS_BUNDLE_PLUGINS "${MACOS_BUNDLE_CONTENTS}/PlugIns")          # Location of the MacOS .app plugins
set(MACOS_BUNDLE_RESOURCES "${MACOS_BUNDLE_CONTENTS}/Resources")      # Location of the MacOS .app resources
set(MY_MACOS_SIGNATURE "${MACOS_CODESIGN_IDENTITY}")    # Baldur van Lew - developer id on Mac M4
set(ENTITLEMENTS_APP "${CMAKE_CURRENT_SOURCE_DIR}/MV_application.entitlements")
set(ENTITLEMENTS_WEBENGINE "${CMAKE_CURRENT_SOURCE_DIR}/webengine.entitlements")



include("${CMAKE_CURRENT_LIST_DIR}/macdeploy_utils.cmake")
# APP_NAME=$APPLICATION_NAME                                      # ManiVault application name
#APP_VERSION=$APPLICATION_VERSION                                # ManiVault application version

	# 1.) Clean up the MacOS bundle by removing any Qt frameworks that may have been included in the Conan package
	prebundle_cleanup()

	# 2.) Make the ManiVault Studio application an executable (+x permission)
	#set_appbundle_executable()

	# 3.) Clean out  any old bundle plugins
	remove_bundle_plugins()

	# 4.) Set intra plugin dependencies to use @loader_path
	fix_plugin_dependencies()

	# 5.) Deploy the MacOS bundle fixing up the rpaths and bundling dependencies
	macdeployqt_bundle()

	# 6.) Make sure all plugins contain an rpath for the PluginDependencies
	add_plugin_dependencies_rpath()

	# 7.) Remove a build rpath from the ManiVault Studio executable
	remove_binary_qt_rpath()

	
	find_program(CODESIGN_EXECUTABLE codesign REQUIRED)

	# Sign the webengine
	message(STATUS "Sign the QtWebEngineProcess")
	execute_process(COMMAND /bin/zsh -c  "${CODESIGN_EXECUTABLE} --force --timestamp --deep --sign -${MY_MACOS_SIGNATURE} --entitlements ${ENTITLEMENTS_WEBENGINE} ${MACOS_BUNDLE_WEBENGINE}")
	
	# Sign the plugins
	message(STATUS "Sign the Plugins")
	execute_process(COMMAND /bin/zsh -c "${CODESIGN_EXECUTABLE} --force --timestamp --sign ${MY_MACOS_SIGNATURE} --entitlements ${ENTITLEMENTS_APP} ${MACOS_BUNDLE}/Plugins/*")

	# Inline script to ad-hoc code-sign the ManiVault Studio.app and Plugins for development purposes
	# Sign the app	

	message(STATUS "Sign the ManiVault Studio.app")
	execute_process(COMMAND /bin/zsh -c  "${CODESIGN_EXECUTABLE} --force --timestamp --deep --sign -{MY_MACOS_SIGNATURE} --entitlements ${ENTITLEMENTS_APP} ${MACOS_BUNDLE_APP}")


