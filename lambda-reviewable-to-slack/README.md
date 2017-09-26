# Integration between Reviewable and Slack.

This integration allows developper to be pinged on Slack when they receive code reviews on pull requests on Github/Reviewable.

# Setup

* Install docker and docker-compose.
* Checkout this code on your machine.
* Run Zappa to deploy this code as a AWS Lambda function: `docker-compose run lambda-reviewable-to-slack-deploy zappa deploy dev`. For more info about how Zappa works [check its documentation](https://github.com/Miserlou/Zappa).
* [Add a new webhook in Github](https://github.com/bayesimpact/paul-emploi/settings/hooks). Enter the url of your freshly created AWS Lambda endpoint, use 'json' for the Content type, and select the individual event 'Issue Comment'.
* Get a personal auth token on Github, then add it as GITHUB_PERSONAL_ACCESS_TOKEN to the [AWS Lambda function environment variables](https://console.aws.amazon.com/lambda/home) to your local machine if you want to test this code locally.

# Lint and Test
If you want to modify this code:

* To test the Flask endpoint of the AWS Lambda function locally:
```
docker-compose run lambda-reviewable-to-slack-test bash
FLASK_APP=reviewable_to_slack.py flask run &
curl -H "Content-Type: application/json" -X POST --data @github_notification_payload_example.json http://127.0.0.1:5000/handle_github_notification
```
* To run the linting and testing:
```
docker-compose run lambda-reviewable-to-slack-test ./lint_and_test.sh`.
```
* To deploy your new code on AWS Lambda:
```
docker-compose run lambda-reviewable-to-slack-deploy bash
zappa update dev
# To get the live debug logs:
zappa tail
```
