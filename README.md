# Bayes developer setup
Tools, files, and other necessary things to get your machine configured for work at Bayes.

## Install

You can install this tool without downloading the repo yourself by downloading and
running `install.sh` (no need to clone the repo yourself). Or simply run the following command: 
	
	sudo curl -s https://raw.githubusercontent.com/bayesimpact/bayes-developer-setup/master/install.sh | bash

Test your installation by verifying that hub was installed correctly.
Running `which hub` should return something like "~/.bayes-developer-setup/bin/hub".

### Common Errors

Hub is not found: This script will automatically write the necessary updates to your .bashrc file. If you use a different file (e.g. .bash_profile) you will need to set up your .bash_profile to read from your .bashrc.

To do this, add the follwing to your .bash_profile:
```
if [ -f ~/.bashrc ]; then
   source ~/.bashrc
fi

```
then run `source ~/.bash_profile` to update. 


## Tests

Run tests for `git-submit` using Docker:

* [Install](http://go/wiki/Docker) docker and docker-compose.
* Run `docker-compose run --rm test`

Run tests for the Reviewable rule using Docker:

* Run `docker-compose run --rm test-reviewable`

During development, you can have the tests be re-executed on any change you make
to the files. In order to do that run the container with:
`docker-compose run --rm test-reviewable npm run test:watch`.

## How to use

To submit a pull request:

* Run `git up` and `git rebase` to make sure your code is up to date with master (this will rebase your code)
* Run `git review [reviewer-username]` to push your branch and open a pull request with the specified reviewer
* To update the code for review after making changes, user `git review -f`
* When your PR is ready to be merged, run `git submit` to merge your PR and delete your local branch
