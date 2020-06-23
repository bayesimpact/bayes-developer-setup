#!/usr/bin/env bash
#
# A script to install a list of suggested apps and packages for Mac users.

# TODO - Queue answers before install.

touch ~/.bashrc
touch ~/.bash_profile


# Propose additional packages for Mac users.
if [ "$(uname)" == "Darwin" ]; then
  read -p "We noticed that you are using Mac. Would you like to add some useful packages with Homebrew? " -n 1 -r
  echo # Add a blank line.
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit
  fi
else
  echo "Sorry, Homebrew is only available for Mac users."
  exit
fi

# Check if Homebrew is installed.
echo 'Install or update Homebrew.'
which -s brew
if [[ $? != 0 ]]; then
  # Install Homebrew.
  /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
  brew update
fi

## Mac apps.
# TODO - Add more context about each app.
echo "Here is a list of suggested apps."
declare -a apps=(
                "1password"
                "docker"
                "firefox"
                "gephi"
                "google-chrome"
                "hipchat"
                "iterm2"
                "java"
                "mou"
                "pgadmin3"
                "postgres"
                "slack"
                "sublime-text"
                "virtual-box"
                "xcode"
                "xquartz"
                )

## Loop through apps.
for app in "${apps[@]}"; do
  if [[ $(system_profiler SPApplicationsDataType | grep -i $app) ]]; then
    echo "$app is already installed."
  else
    read -p "Would you like to install $app? " -n 1 -r
    echo # Add a blank line.
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      brew cask install $app
      if [[ $app == "xcode" ]]; then
        # Install Xcode.
        if [[ "$(xcode-select -p)" ]]; then
          echo 'Xcode is already installed.' >&2
        else
          echo 'Installing Xcode.' >&2
          xcode-select --install
        fi
      elif [[ $app == "postgres" ]]; then
        echo 'export PATH="~/Applications/Postgres.app/Contents/Versions/latest/bin/:$PATH"' >> ~/.bash_profile
      elif [[ $app == "sublime-text" ]]; then
        echo 'We are in the right place.'
        alias subl="/Applications/Sublime\ Text.app/Contents/SharedSupport/bin/subl"
        echo 'subl is now an alias for sublime-text !'
        read -p "Would you like to make sublime your default git editor? " -n 1 -r
        echo # Add a blank line.
        if [[ $REPLY =~ ^[Yy]$ ]]; then
          git config --global core.editor '"/Applications/Sublime Text.app/Contents/SharedSupport/bin/subl" -w'
        fi
      fi
    fi
  fi
done

## Mac packages.
# TODO(cyrille): Use associative array to add context on prompt.
echo "Here is a list of useful packages."
declare -a packages=(
  "bash-completion: Autocompletion for CLI in bash."
  "coreutils: GNU utils instead of FreeBSD (default) ones. Used in several Bayes scripts."
  "gcc: C/C++/Go compiler."
  "graphviz: Graph manipulator."
  "imagemagick: Image manipulator."
  "jq: JSON manipulator. Used in several Bayes scripts."
  "mongodb: MongoDB client (and server?)."
  "pyenv: Python environment manager."
  "terminal-notifier: Notifications for Terminal."
  "wget: Downloading content from the web. Used in some Bayes scripts."
)

## Loop through packages.
for package_with_desc in "${packages[@]}"; do
  package=$(echo "$package_with_desc" | cut -f1 -d:)
  if which $package > /dev/null || brew list $package >/dev/null 2>&1; then
    continue
  fi
  echo "$package_with_desc"
  read -p "Would you like to install it? " -n 1 -r
  echo # Add a blank line.
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    continue
  fi
  brew install "$package"
  if [[ "$package" == "pyenv" ]]; then
    brew install openssl readline sqlite3 xz zlib
    if ! grep pyenv "$HOME/.bash_profile" || ! grep pyenv "$HOME/.bashrc"; then
      printf '# Use pyenv to manage python versions.\nif command -v pyenv 1>/dev/null 2>&1; then\n  eval "$(pyenv init -)"\nfi\n' >> "HOME/.bash_profile"
    fi
    readonly LATEST_PYTHON="$(pyenv install --list | grep -v - | tail -n 1)"
    pyenv install "$LATEST_PYTHON"
    pyenv global "$LATEST_PYTHON"
  fi
done
