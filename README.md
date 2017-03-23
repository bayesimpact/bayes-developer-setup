# Bayes developer setup
Tools, files, and other necessary things to get your machine configured for work at Bayes.

## Install

You can install this tool without downloading the repo yourself by downloading and
running `install.sh` (no need to clone the repo yourself). Test your installation by verifying that hub was installed correctly.
Running `which hub` should return something like "/Users/[username]/.bayes-developer-setup/bin/hub".

**Note**: This script will automatically write the necessary updates to your .bashrc file. If you use a different file (e.g. .bash_profile) you will need to move the information after install using `cat ~/.bashrc >> ~./bash_profile`. 
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

The first time you use bayes-developer-setup you'll have to login to Github. 

* Run `hub issue` and login using your username, password, and 2fa code.

To submit a pull request:

* Run `git up` or `git rebase` to make sure your code is up to date with master (this will rebase your code)
* Run `git review [reviewer-username]` to push your branch and open a pull request with the specified reviewer
* When your PR is ready to be merged, run `git submit` to merge your PR and delete your local branch


