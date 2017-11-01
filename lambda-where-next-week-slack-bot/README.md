# Where Next Week Slack bot
Slack bot that tells the team in which city team members will be next week. Useful for teams that travel a lot!

# Setup
This setup needs to be done once per organization on Slack:

* Install docker and docker-compose.
* Checkout this code on your machine.
* Run Zappa to deploy this code as an AWS Lambda function: `docker-compose run lambda-where-next-week-slack-bot-deploy zappa deploy dev`. For more info about how Zappa works [check its documentation](https://github.com/Miserlou/Zappa).

# Lint and Test
If you want to modify this code:

* To manually test the Flask endpoint of the AWS Lambda function locally:
```
docker-compose run lambda-where-next-week-slack-bot-test bash
./manual_flask_test/test-flask-endpoint.sh issue_comment manual_flask_test/test_payloads/github_notification_issue_comment.json
```
* To run the linting and testing:
```
docker-compose run lambda-where-next-week-slack-bot-test ./lint_and_test.sh`.
```
* To deploy your new code on AWS Lambda:
```
docker-compose run lambda-where-next-week-slack-bot-deploy bash
zappa update dev
# To get the live debug logs:
zappa tail
```
