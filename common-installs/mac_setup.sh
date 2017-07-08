#!/usr/bin/env bash

touch ~/.bashrc
touch ~/.bash_profile

# Install Xcode.
if [[ "$(xcode-select -p)" ]]; then
  echo 'Xcode is already installed.' >&2
else
  echo 'Installing Xcode.' >&2
  xcode-select --install
fi

## Mac apps.
echo "Here is a list of useful apps."
declare -a arr=("google-chrome"
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
for i in "${arr[@]}"
do
    read -p "Would you like to install $i? " -n 1 -r
    echo # Add a blank line.
    if [[ $REPLY =~ ^[Yy]$ ]]
    then
        brew cask install $i
        if [[ $i == "postgres" ]]
        then
            echo 'export PATH="~/Applications/Postgres.app/Contents/Versions/latest/bin/:$PATH"' >> ~/.bash_profile
        elif [[ $i == "sublime-text" ]]
        then
          echo 'We are in the right place.'
          alias subl="/Applications/Sublime\ Text.app/Contents/SharedSupport/bin/subl"
          echo 'subl is now an alias for sublime-text !'
          read -p "Would you like to make sublime your default git editor? " -n 1 -r
          echo # Add a blank line.
          if [[ $REPLY =~ ^[Yy]$ ]]
          then
            git config --global core.editor '"/Applications/Sublime Text.app/Contents/SharedSupport/bin/subl" -w'
          fi
        fi
    fi
done


## Mac packages.
echo "Here is a list of useful packages."

declare -a arr=("wget" 
                "mongodb"
                "graphviz"
                "imagemagick"
                "terminal-notifier"
                "gcc"
                )

## Loop through packages.
for i in "${arr[@]}"
do
   read -p "Would you like to install $i? " -n 1 -r
   echo # Add a blank line.
if [[ $REPLY =~ ^[Yy]$ ]]
then
    brew install "$i"
fi
done
