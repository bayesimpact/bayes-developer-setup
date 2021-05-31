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
git fetch --depth=1 origin master && git reset --hard origin/master 2> /dev/null > /dev/null

# Rerun this script every week to make sure it keeps everything up-to-date.
if [ -x "$(which anacron)" ]; then
  # Check if already in anacron.
  grep -qF "${DIR}/install.sh" /etc/anacrontab 2> /dev/null
  if [ $? -ne 0 ]; then
    if [ -x "$(which crontab)" ]; then
      # Drop cron job, if it exists.
      crontab -l | grep -qF "${DIR}/install.sh" 2> /dev/null &&
        crontab -l | grep -vF "${DIR}/install.sh" | crontab -
    fi
    echo 'Adding this script in anacrontab for auto-update.'
    echo "7    15    org.bayes.setup.install    ${SHELL} ${DIR}/install.sh" >> /etc/anacrontab
  fi
elif [ -x "$(which launchctl)" ]; then
  # Check if already in launchd.
  launchctl list | grep -qF "org.bayes.setup.install" 2> /dev/null
  if [ $? -ne 0 ]; then
    if [ -x "$(which crontab)" ]; then
      # Drop cron job, if it exists.
      crontab -l | grep -qF "${DIR}/install.sh" 2> /dev/null &&
        crontab -l | grep -vF "${DIR}/install.sh" | crontab -
    fi
    echo 'Adding this script in launchd for auto-update.'
    mkdir -p "$DIR/logs"
    sed "s~{{DIR}}~$DIR~" org.bayes.setup.install.plist |
      sed "s~{{SHELL}}~$SHELL~" > ${HOME}/Library/LaunchAgents/org.bayes.setup.install.plist
    launchctl load ${HOME}/Library/LaunchAgents/org.bayes.setup.install.plist
  fi
elif [ -x "$(which crontab)" ]; then
  # Check if already in crontab.
  readonly TMP_CRON=$(mktemp)
  crontab -l 2> /dev/null > "${TMP_CRON}"
  grep -qF "${DIR}/install.sh" "${TMP_CRON}" &2 /dev/null
  if [ $? -ne 0 ]; then
    echo 'Adding this script in crontab for auto-update.'
    echo "@weekly ${SHELL} ${DIR}/install.sh" >> "${TMP_CRON}"
    crontab "${TMP_CRON}"
  fi
  rm "${TMP_CRON}"
fi

readonly SHELLRC="${HOME}/.${SHELL#*/bin/}rc"
function add_to_shellrc {
  local label=$1
  local line=$2

  local marker="  # ${NAME} ${label}"

  sed -i -e "/${marker}/d" "${SHELLRC}" 2> /dev/null
  echo "${line}${marker}" >> "${SHELLRC}"

  if [ "$(uname)" == "Darwin" ] && ! grep -q $SHELLRC "$HOME/.bash_profile"; then
    printf "if [ -f \"$SHELLRC\" ]; then\n  source $SHELLRC\nfi\n" >> "$HOME/.bash_profile"
  fi
}

# Specify scripts' source
add_to_shellrc 'installation.' ''

# Install binaries.
add_to_shellrc 'bin' "if [[ \":\$PATH:\" != *\":$DIR/bin:\"* ]]; then export PATH=\"\$PATH:$DIR/bin\"; fi"
export PATH="$PATH:$DIR/bin"

# Install manuals.
add_to_shellrc 'man' "MANPATH=\$(manpath 2> /dev/null); if [[ \":\$MANPATH:\" != *\":$DIR/man:\"* ]]; then export MANPATH=\"\$MANPATH:$DIR/man\"; fi"

# Install autocompletions.
if [ "$(uname)" == "Darwin" ] && [ -n "$(which brew)" ] && [ -x "$(which brew)" ] && (brew list | grep bash-completion > /dev/null); then
  AUTOCOMPLETE_PATH="$(brew --prefix)/etc/bash_completion.d"
elif [ "$(uname)" == "Linux" ]; then
  AUTOCOMPLETE_PATH="/usr/share/bash-completion/completions/"
fi
if [ -d "$AUTOCOMPLETE_PATH" ]; then
  # TODO(cyrille): Put the completion scripts in a subfolder.
  for completion_file in $(ls *.bash_completion); do
    ln -s $DIR/$completion_file "$AUTOCOMPLETE_PATH/${completion_file%".bash_completion"}" 2> /dev/null
  done
fi

# Install hub.
HUB_VERSION="2.14.2"
if [ -z "$(which hub)" ] || [ "$(hub --version | grep hub\ version | sed -e "s/.* //")" != "${HUB_VERSION}" ]; then

  if [ "$(uname)" == "Darwin" ]; then
    HUB_PLATFORM="darwin-amd64"
  fi
  if [ "$(uname)" == "Linux" ] && [ "$(uname -p)" == "x86_64" ]; then
    HUB_PLATFORM="linux-amd64"
  fi
  if [ -n "${HUB_PLATFORM}" ]; then
    TEMP_TGZ="$(mktemp)"
    TEMP_DIR="$(mktemp -d)"
    curl -o "$TEMP_TGZ" -L "https://github.com/github/hub/releases/download/v${HUB_VERSION}/hub-${HUB_PLATFORM}-${HUB_VERSION}.tgz"
    tar -zxf "$TEMP_TGZ" -C "$TEMP_DIR"
    prefix="$DIR" "$TEMP_DIR/hub-${HUB_PLATFORM}-${HUB_VERSION}/install"
    rm "$TEMP_TGZ"; rm -r "$TEMP_DIR"
  else
    # There's no easy way to install a recent version of hub: we then create a
    # stub with instructions to install it.
    echo "#!${SHELL}" > "$DIR/bin/hub"
    echo "echo Please install hub from https://github.com/github/hub" >> "$DIR/bin/hub"
    echo "exit 1" >> "$DIR/bin/hub"
    chmod +x "$DIR/bin/hub"
  fi
fi

# Check if user is in interactive mode,
# likely using this script for the first time.
if [[ "$-" != "${-#*i}" ]]; then
  echo "This shell is not interactive, exiting."
else
  # Check if the user is logged in.
  echo "Checking hub setup."
  hub ci-status
  if [ "$(hub ci-status)" == "success" ]; then
    echo "Hub is setup successfully.";
  else
    echo "Make sure you are signed into hub.";
  fi
  # Propose Github add-ons.
  ./common-installs/github_tools.sh

  # Propose Mac apps and packages.
  if [ "$(uname)" == "Darwin" ]; then
    ./common-installs/mac_setup.sh
  fi

  AUTOCOMPLETE_PATH="$AUTOCOMPLETE_PATH" ./common-installs/pip_setup.sh
  # TODO(cyrille): Add lint npm packages.
fi
