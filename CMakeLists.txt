cmake_minimum_required(VERSION 3.10)
project(jackal_network_bringup)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY
    config
    docs
    launch
  DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)

install(
  FILES README.md
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS
    scripts/check_network.sh
    scripts/cmd_vel_safety_bridge.py
    scripts/network_probe.py
    scripts/network_verifier.py
    scripts/twist_stamper.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)

  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
  ament_add_pytest_test(
    config_and_launch_test
    test/test_config_and_launch.py
    TIMEOUT 60
  )
endif()

ament_package()
