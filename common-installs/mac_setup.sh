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
                    # Autocompletion for CLI in bash.
                    "bash-completion"
                    # GNU utils instead of FreeBSD (default) ones. Used in several Bayes scripts.
                    "coreutils"
                    # C/C++/Go compiler.
                    "gcc"
                    "graphviz"
                    # Image manipulator.
                    "imagemagick"
                    # JSON manipulator. Used in several Bayes scripts.
                    "jq"
                    # MongoDB client (and server?).
                    "mongodb"
                    # Python environment manager.
                    "pyenv"
                    "terminal-notifier"
                    # Downloading content from the web. Used in some Bayes scripts.
                    "wget"
                    )

## Loop through packages.
for package in "${packages[@]}"; do
  if ! which $package > /dev/null; then
    read -p "Would you like to install $package? " -n 1 -r
    echo # Add a blank line.
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      brew install "$package"
    fi
  fi
done
