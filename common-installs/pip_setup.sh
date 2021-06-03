#!/usr/bin/env bash
#
# Setting up pip packages.

if ! pip --version | grep -q 'python 3'; then
    echo "Sorry, pip installs are only useful for python3 users."
    exit 1
fi

function install_if_agree() {
    local question=$1
    shift
    local has_missing_package
    for package in $@; do
      if ! pip show -qq $package; then
        has_missing_package=1
        break
      fi
    done
    if [ -z "$has_missing_package" ]; then
      return
    fi
    read -p "$question " -n 1 -r
    echo # Add a blank line.
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      pip install $@
    else
      return 1
    fi
}

install_if_agree "Installing unidecode for git-review..." unidecode <<< 'y'

install_if_agree "Would you like to install linters for python code?" \
    "pycodestyle" \
    "pylint" \
    "pylint-quotes" \
    "pylint-doc-spacing" \
    "pylint-import-modules"

install_if_agree "Would you like to install AWS CLI? " awscli

if install_if_agree "Would you like to install auto-completion for python scripts?" argcomplete; then
  activate-global-python-argcomplete --dest "$AUTOCOMPLETE_PATH"
fi
