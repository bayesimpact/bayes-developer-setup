#!/bin/bash

set -e

readonly SHELL="/bin/bash"
pipenv shell

$@
