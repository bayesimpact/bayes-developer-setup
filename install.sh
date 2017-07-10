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

# Specify scripts' source
add_to_shellrc 'installation.' ''

# Install binaries.
add_to_shellrc 'bin' "if [[ \":\$PATH:\" != *\":$DIR/bin:\"* ]]; then export PATH=\"\$PATH:$DIR/bin\"; fi"

# Install manuals.
add_to_shellrc 'man' "MANPATH=\$(manpath 2> /dev/null); if [[ \":\$MANPATH:\" != *\":$DIR/man:\"* ]]; then export MANPATH=\"\$MANPATH:$DIR/man\"; fi"


# Install hub.
HUB_VERSION="2.3.0-pre8"
if [ -z "$(which hub)" ] || [ "$(hub --version | grep hub\ version | sed -e "s/.* //")" != "${HUB_VERSION}" ]; then

  if [ "$(uname)" == "Darwin" ]; then
    HUB_PLATFORM="darwin-amd64"
  fi
  if [ "$(uname)" == "Linux" ] && [ "$(uname -p)" == "x86_64" ]; then
    HUB_PLATFORM="linux-amd64"
  fi
  if [ -n "${HUB_PLATFORM}" ]; then
    if [ "${HUB_PLATFORM}" == "darwin-amd64" ]; then
      curl -O "https://github.com/github/hub/releases/download/v${HUB_VERSION}/hub-${HUB_PLATFORM}-${HUB_VERSION}.tgz"
      tar -zxf "hub-${HUB_PLATFORM}-${HUB_VERSION}.tgz" -C "${DIR}" --strip-components 1 "hub-${HUB_PLATFORM}-${HUB_VERSION}"/bin
    else
      wget "https://github.com/github/hub/releases/download/v${HUB_VERSION}/hub-${HUB_PLATFORM}-${HUB_VERSION}.tgz" -O - | \
        tar xz -C "${DIR}" --strip-components 1 "hub-${HUB_PLATFORM}-${HUB_VERSION}/bin" -C "${DIR}" --strip-components 1
    fi
  else
    # There's no easy way to install a recent version of hub: we then create a
    # stub with instructions to install it.
    echo "#!${SHELL}" > "$DIR/bin/hub"
    echo "echo Please install hub from https://github.com/github/hub" >> "$DIR/bin/hub"
    echo "exit 1" >> "$DIR/bin/hub"
    chmod +x "$DIR/bin/hub"
  fi
fi


# Check if the user is logged in.
if [ "$(hub ci-status)" == "success" ]; then
  echo "Hub is setup successfully.";
else
  echo "Make sure you are signed into hub.";
fi


# Check if user is in interactive mode,
# likely using this script for the first time.
if [[ "$-" != "${-#*i}" ]]; then
  echo "This shell is not interactive, exiting."
else
  # Propose Github add-ons.
  ./common-installs/github_tools.sh

  # Propose Mac apps and packages.
  if [ "$(uname)" == "Darwin" ]; then
    ./common-installs/mac_setup.sh
  fi
fi
