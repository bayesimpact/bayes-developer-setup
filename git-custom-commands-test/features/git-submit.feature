Feature: git submit

  Background:
    # TODO(pascal): Also add tests for the default (without this env var).
    Given I set the environment variable "NO_GIT_SUBMIT_EXPERIMENTAL" to "1"

