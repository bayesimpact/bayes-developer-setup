Feature: git submit

  Scenario: Successful submission
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "master"
    And I commit a file "successful submission"
    And I successfully run `git push -u origin success`
    When I run `git submit`
    Then the exit status should be 0
    And I should be on "master" git branch
    And the "success" git branch should not exist
    And the "success" git branch in "origin" should not exist
    And the "master" git branch should be in sync with the "master" git branch in "origin"
    And the file "successful submission" should exist

  Scenario: Prevent submission if never reviewed
    Given a dummy git repo in "origin"
    And I am in a "work" git repo cloned from "origin"
    And I create a "success" git branch from "master"
    And I commit a file "successful submission"
    When I run `git submit`
    Then the exit status should not be 0
    And the output should contain "The branch success is not tracked and has probably never been reviewed."
    And I should be on "success" git branch
    And the "success" git branch in "origin" should not exist
    And the "master" git branch should be in sync with the "master" git branch in "origin"
    And the file "successful submission" should exist
