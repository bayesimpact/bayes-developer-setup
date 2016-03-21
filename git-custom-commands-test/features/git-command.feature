Feature: git commands

  Scenario: known command
    When I run `git help`
    Then the exit status should be 0

  Scenario: unknown command
    When I run `git foobar`
    Then the exit status should not be 0
    And the output should contain "'foobar' is not a git command"

  Scenario: submit command
    When I run `git submit`
    Then the exit status should not be 0
    But the output should not contain "is not a git command"

  Scenario: submit command
    When I run `git review`
    Then the exit status should not be 0
    But the output should not contain "is not a git command"
