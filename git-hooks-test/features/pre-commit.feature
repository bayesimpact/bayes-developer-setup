Feature: pre-commit

  # TODO(cyrille): Add real tests.
  Background:
    Given I use the defined hook "pre-commit"

  Scenario: Successful commit
    Given I am in a dummy git repo in "repo"
    When I commit a file "successful submission" with message:
      """
      [Topic] Message subject.
      """
    Then the exit status should be 0
    And I should be on "main" git branch
    And the file "successful submission" should exist
    And the git status should be clean

  Scenario: Can commit new files
    Given I am in a dummy git repo in "repo"
    And I am in a Bazel repo
    And a file named "my_file.py" with:
      """
      print('Hello world!')
      """
    And a file named "BUILD" with:
      """
      py_library(
        name = "my_file",
        srcs = ["my_file.py"],
      )
      """
    When I commit everything
    Then the exit status should be 0
    And the git status should be clean

  Scenario: Can commit new files without imports
    Given I am in a dummy git repo in "repo"
    And I am in a Bazel repo
    And a file named "my_file.txt" with:
      """
      Hello World!
      """
    And a file named "BUILD" with:
      """
      filegroup(
        name = "my_file",
        srcs = ["my_file.txt"],
      )
      """
    When I commit everything
    Then the exit status should be 0
    And the git status should be clean

  Scenario: Can commit new empty __init__ files
    Given I am in a dummy git repo in "repo"
    And I am in a Bazel repo
    And an empty file named "__init__.py"
    When I commit everything
    Then the exit status should be 0
    And I should be on "main" git branch
    And the file "__init__.py" should exist
    And the git status should be clean
