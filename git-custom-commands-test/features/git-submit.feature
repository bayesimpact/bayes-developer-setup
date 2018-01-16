Feature: git submit

  Background:
    # TODO(pascal): Also add tests for the default (without this env var).
    Given I set the environment variable "NO_GIT_SUBMIT_EXPERIMENTAL" to "1"

  Scenario: Successful submission
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "master"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    And I successfully run `git push -u origin success`
    When I run `git submit`
    Then the exit status should be 0
    And I should be on "master" git branch
    And the "success" git branch should not exist
    And the "success" git branch in "origin" should not exist
    And the "master" git branch should be in sync with "master" in "origin"
    And the file "successful submission" should exist

  Scenario: Prevent submission if never reviewed
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "master"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    When I run `git submit`
    Then the exit status should not be 0
    And the output should contain "The branch success is not tracked and has probably never been reviewed."
    And I should be on "success" git branch
    And the "success" git branch in "origin" should not exist
    And the "master" git branch should be in sync with "master" in "origin"
    And the file "successful submission" should exist

  Scenario: Branch to submit is late compared to origin/master
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And a file "other dev" is committed on "master" git branch in "origin" with:
      """
      Whatever
      """
    And I create a "success" git branch from "master"
    And I commit a file "successful submission" with:
      """
      Something else
      """
    And I successfully run `git push -u origin success`
    When I run `git submit`
    Then the exit status should be 0
    And I should be on "master" git branch
    And the "success" git branch should not exist
    And the "success" git branch in "origin" should not exist
    And the "master" git branch should be in sync with "master" in "origin"
    And the file "successful submission" should exist
    And the file "other dev" should exist

  Scenario: Merge conflict on submission
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And a file "conflict" is committed on "master" git branch in "origin" with:
      """
      Whatever
      """
    And I create a "success" git branch from "master"
    And I commit a file "conflict" with:
      """
      Something else
      """
    And I successfully run `git push -u origin success`
    When I run `git submit`
    Then the exit status should not be 0
    And the output should contain "Merge conflict"
    And I should be on "success" git branch
    And the "success" git branch in "origin" should still exist
    And the "master" git branch should be in sync with "master^" in "origin"
    And the file "conflict" should contain "Something else"
