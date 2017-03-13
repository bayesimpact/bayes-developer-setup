# Bayes developer setup
Tools, files, and other necessary things to get your machine configured for work at Bayes.

## Install

Make sure that you are logged-in to the github.com to run hub commands. You can test this by running a random hub command like

    hub issue

Log in with your github username and password. No need to create Access Tokens.

You can install this tool without downloading the repo yourself by downloading and
running `install.sh` (no need to clone the repo yourself).

## Tests

Run tests for `git-submit` using Docker:

* [Install](http://go/wiki/Docker) docker and docker-compose.
* Run `docker-compose run --rm test`

Run tests for the Reviewable rule using Docker:

* Run `docker-compose run --rm test-reviewable`

During development, you can have the tests be re-executed on any change you make
to the files. In order to do that run the container with:
`docker-compose run --rm test-reviewable npm run test:watch`.
