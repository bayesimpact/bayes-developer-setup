#!/usr/bin/env bash
#
# Setting up pip packages.

if ! pip --version | grep 'python 3'; then
    echo "Sorry, pip installs are only useful for python3 users."
    exit 1
fi

function install_if_agree() {
    local question=$1
    shift
    read -p "$question " -n 1 -r
    echo # Add a blank line.
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      pip install $@
    fi
}

install_if_agree "Would you like to install linters for python code?" \
    "pycodestyle" \
    "pylint" \
    "pylint-quotes" \
    "pylint-doc-spacing" \
    "pylint-import-modules"

install_if_agree "Would you like to install AWS CLI? " awscli
