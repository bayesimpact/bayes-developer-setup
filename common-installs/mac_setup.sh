#!/usr/bin/env bash
#
# A script to install a list of suggested apps and packages for Mac users.

touch ~/.bashrc
touch ~/.bash_profile


# Propose additional packages for Mac users.
if [ "$(uname)" == "Darwin" ]; then
  read -p "We noticed that you are using Mac. Would you like to add some useful packages with Homebrew? " -n 1 -r
  echo # Add a blank line.
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./common-installs/mac_setup.sh
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
echo "Here is a list of suggested apps."
declare -a apps=("xcode"
                "google-chrome"
                "docker"
                "1password"  
                "firefox"
                "mou"
                "slack"
                "iterm2"
                "xquartz"
                "virtual-box"
                "sublime-text"
                "postgres"
                "pgadmin3"
                "gephi"
                "java"
                )

## Loop through apps.
for app in "${apps[@]}"; do
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
done

## Mac packages.
echo "Here is a list of useful packages."
declare -a packages=("wget" 
                "mongodb"
                "graphviz"
                "imagemagick"
                "terminal-notifier"
                "gcc"
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
