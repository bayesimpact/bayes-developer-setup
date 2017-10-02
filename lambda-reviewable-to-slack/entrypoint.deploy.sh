#!/bin/bash

set -e

export SHELL="/bin/bash"
pipenv shell

$@
