Feature: git review

  Background:
    # TODO(pascal): Also add tests for the default (without this env var).
    Given I set the environment variable "GIT_REVIEW_EXPERIMENTAL_PYTHON" to "1"
    And I run `git config --global user.email username@example.com`

  Scenario: Create a branch on main
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I commit a file "successful submission" with message "whatever" and content:
      """
      Whatever
      """
    When I run `git review`
    Then the exit status should be 0
    And I should be on "whatever" git branch
    And the "username-whatever" git branch in "origin" should exist
    And the "main" git branch should be in sync with "main" in "origin"
    And the file "successful submission" should exist
