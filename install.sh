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
  git remote add origin git@github.com:bayesimpact/bayes-developer-setup.git
fi

# Refresh repo.
git pull origin master
git reset --hard

# Check if already in crontab.
readonly TMP_CRON=$(mktemp)
crontab -l 2> /dev/null > "${TMP_CRON}"
grep -F "${DIR}/install.sh" "${TMP_CRON}" > /dev/null
if [ $? -ne 0 ]; then
  echo 'Adding this script in crontab for auto-update.'
  echo "@weekly ${DIR}/install.sh" >> "${TMP_CRON}"
  crontab "${TMP_CRON}"
fi
rm "${TMP_CRON}"

readonly BASHRC="${HOME}/.bashrc"
function add_to_bashrc {
  local label=$1
  local line=$2

  local marker="  # ${NAME} ${label}"

  sed -i "/${marker}/d" "${BASHRC}" 2> /dev/null
  echo "${line}${marker}" >> "${BASHRC}"
}

# Install binaries.
add_to_bashrc 'bin' "export PATH=\"\$PATH:$DIR/bin\""

# Install manuals.
add_to_bashrc 'man' "export MANPATH=\"\$(manpath):$DIR/man\""
