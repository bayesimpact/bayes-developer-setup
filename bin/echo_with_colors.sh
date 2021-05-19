#!/usr/bin/env bash
# Helpers to echo strings with colors to stderr.
function echo_error {
  # Red.
  >&2 echo -e "\033[31mERROR: $1\033[0m"
}

function echo_success {
  # Green.
  >&2 echo -e "\033[32m$1\033[0m"
}

function echo_warning {
  # Orange.
  >&2 echo -e "\033[33m$1\033[0m"
}

function echo_info {
  # Blue.
  >&2 echo -e "\033[36m$1\033[0m"
}
