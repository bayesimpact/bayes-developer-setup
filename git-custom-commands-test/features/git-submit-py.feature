Feature: git submit

  Background:
    Given I set the environment variable "NO_GIT_SUBMIT_EXPERIMENTAL" to "1"
    Given I set the environment variable "GIT_SUBMIT_EXPERIMENTAL_PYTHON" to "1"

  Scenario: Successful submission
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "main"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    And I successfully run `git push -u origin success`
    When I run `git submit`
    Then the exit status should be 0
    And I should be on "main" git branch
    And the "success" git branch should not exist
    And the "success" git branch in "origin" should not exist
    And the "main" git branch should be in sync with "main" in "origin"
    And the file "successful submission" should exist

  Scenario: Prevent submission if never reviewed
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "main"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    When I run `git submit`
    Then the exit status should not be 0
    And the output should contain "The branch success is not tracked and has probably never been reviewed."
    And I should be on "success" git branch
    And the "success" git branch in "origin" should not exist
    And the "main" git branch should be in sync with "main" in "origin"
    And the file "successful submission" should exist

  Scenario: Bypass Y/N questions
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "main"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    When I run `git submit`
    Then the exit status should not be 0
    And the output should contain "not a TTY"

  Scenario: Branch to submit is late compared to origin/main
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And a file "other dev" is committed on "main" git branch in "origin" with:
      """
      Whatever
      """
    And I create a "success" git branch from "main"
    And I commit a file "successful submission" with:
      """
      Something else
      """
    And I successfully run `git push -u origin success`
    When I run `git submit`
    Then the exit status should be 0
    And I should be on "main" git branch
    And the "success" git branch should not exist
    And the "success" git branch in "origin" should not exist
    And the "main" git branch should be in sync with "main" in "origin"
    And the file "successful submission" should exist
    And the file "other dev" should exist

  Scenario: Merge conflict on submission
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And a file "conflict" is committed on "main" git branch in "origin" with:
      """
      Whatever
      """
    And I create a "success" git branch from "main"
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
    And the "main" git branch should be in sync with "main^" in "origin"
    And the file "conflict" should contain "Something else"

  Scenario: Change default branch name
    Given a dummy git repo in "origin" whose default branch is "default"
    And I am in a "work" git repo cloned from "origin"
    And I should be on "default" git branch
    And I create a "feature" git branch from "default"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    And I successfully run `git push -u origin feature`
    When I run `git submit`
    Then the exit status should be 0
    And I should be on "default" git branch

  Scenario: Abort a submission
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "main"
    And I commit a file "successful submission" with:
      """
      Whatever
      """
    And I run `bash -c 'echo $-'`
    When I run `git push -u origin success:cyrille-success`
    Then the exit status should be 0
    And I successfully run `git checkout main`
    And I successfully run `git branch -D success`
    And I run `git submit -u cyrille -a success`
    Then the exit status should be 0
    And I should be on "success" git branch
    And the "success" git branch should be in sync with "cyrille-success" in "origin"
