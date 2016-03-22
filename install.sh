#!/bin/bash
#
# A script to install and regularly update tools in this repo.
#
# It creates a clone of this repo in ~/.bayes-developer-setup and keep it up to
# date.
#
# It adds the bin folder to the path and the man folder to the manual.

readonly NAME='bayes-developer-setup'

which git > /dev/null
if [ $? -ne 0 ]; then
  echo 'Install git first.' >&2
  exit 1
fi

if [ -z "${HOME}" ]; then
  echo 'Set a HOME env variable so I can decide where to install.' >&2
  exit 2
fi

readonly DIR="${HOME}/.${NAME}"
echo "Creating ${DIR}"
mkdir -p "${DIR}"
cd "${DIR}"

# Check if initial install was ever done.
git rev-parse 2> /dev/null
if [ $? -ne 0 ]; then
  echo 'First install, connecting to git.'
  git init
  git remote add origin https://github.com/bayesimpact/bayes-developer-setup.git
fi

# Refresh repo.
echo "Pulling latest version from GitHub."
git pull origin master 2> /dev/null > /dev/null

# Check if already in crontab.
readonly TMP_CRON=$(mktemp)
crontab -l 2> /dev/null > "${TMP_CRON}"
grep -F "${DIR}/install.sh" "${TMP_CRON}" > /dev/null
if [ $? -ne 0 ]; then
  echo 'Adding this script in crontab for auto-update.'
  echo "@weekly ${SHELL} ${DIR}/install.sh" >> "${TMP_CRON}"
  crontab "${TMP_CRON}"
fi
rm "${TMP_CRON}"

readonly SHELLRC="${HOME}/.${SHELL#/bin/}rc"
function add_to_shellrc {
  local label=$1
  local line=$2

  local marker="  # ${NAME} ${label}"

  sed -i -e "/${marker}/d" "${SHELLRC}" 2> /dev/null
  echo "${line}${marker}" >> "${SHELLRC}"
}

# Install binaries.
add_to_shellrc 'bin' "if [[ \":\$PATH:\" != *\":$DIR/bin:\"* ]]; then export PATH=\"\$PATH:$DIR/bin\"; fi"

# Install manuals.
add_to_shellrc 'man' "MANPATH=\$(manpath 2> /dev/null); if [[ \":\$MANPATH:\" != *\":$DIR/man:\"* ]]; then export MANPATH=\"\$MANPATH:$DIR/man\"; fi"

# Install hub.
if [ -z "$(which hub)" ]; then
  if [ -x "$(which brew)" ]; then
    brew install hub
  else
    # There's no easy way to install a recent version of hub: we then create a
    # stub with instructions to install it.
    echo "#!${SHELL}" > "$DIR/bin/hub"
    echo "echo Please install hub from https://github.com/github/hub" >> "$DIR/bin/hub"
    echo "exit 1" >> "$DIR/bin/hub"
    chmod +x "$DIR/bin/hub"
  fi
fi

# OSX specific setup
readonly DOCKER_OSX_VM_CONFIG="${HOME}/.docker/machine/machines/default/config.json"
readonly DOCKER_OSX_VM_SO_URL='http://stackoverflow.com/questions/34296230/how-to-change-default-docker-machines-dns-settings'
if [ $("uname") == "Darwin" ]; then
  echo "You're on a Mac. Doing OSX-specific thingies."
  if [ -z "$(which ruby)"]; then
    echo "Installing Ruby and RVM"
    \curl -sSL https://get.rvm.io | bash -s stable
  fi
  if [ -z "$(which brew)" ]; then
    echo "Installing HomeBrew and Cask"
    ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    brew install caskroom/cask/brew-cask
  fi
  if [ -z "$(docker-machine)" ]; then
    echo "Installing docker toolbox (docker-machine, etc)"
    brew cask install dockertoolbox
  fi
  if [ -e "${DOCKER_OSX_VM_CONFIG}" ]; then
    echo "Adjusting DNS settings on docker-machine default VM"
    echo `pwd`
    echo python fix_docker_osx_vm_config.py "${DOCKER_OSX_VM_CONFIG}"
    ./fix_docker_osx_vm_config.py "${DOCKER_OSX_VM_CONFIG}"
  else
    echo "Could not find ${DOCKER_OSX_VM_CONFIG}"
    echo "You may have issues with using Docker Registry in your docker-machine"
    echo "If so, read ${DOCKER_OSX_VM_SO_URL}"
    exit 1
  fi
else
  echo "You're NOT on a Mac (uname = $(uname)) - nothing else to do"
fi


