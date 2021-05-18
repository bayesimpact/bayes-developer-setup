Feature: commit-msg

  Background:
    Given I use the defined hooks

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

  Scenario:
    Given I am in a dummy git repo in "repo"
    When I commit a file "new file" with message:
      """
      [topic] Message subject.
      """
    Then the exit status should not be 0
    And the stderr should contain "Title Case"
