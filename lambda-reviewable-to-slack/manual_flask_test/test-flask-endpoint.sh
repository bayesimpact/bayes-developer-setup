#!/bin/bash

# (Re)start Flask app and test sending a payload against the endpoint that receives Github
# notifications.
# Usage:
# ./test-flask-endpoint issue_comment github_notification_issue_comment.json
EVENT_TYPE_TO_TEST="$1"
PAYLOAD_TO_TEST="$2"

# As auto-reload of Flask doesn't work inside the Docker container, we restart the Flask process.
echo $(ps)
FLASK_PID=$(ps | sed -n '/[^-]flask[^-]/p' | sed 's/^ \+\([0-9]\+\).*/\1/')
if [ -n "$FLASK_PID" ]; then
  echo $FLASK_PID
  kill $FLASK_PID
fi

export FLASK_APP=../reviewable_to_slack.py
flask run &

# Give time to Flash to start
sleep 1

RESPONSE=$(curl -X POST -H "X-GitHub-Event: $EVENT_TYPE_TO_TEST" -H "Content-Type: application/json" --data @$PAYLOAD_TO_TEST http://127.0.0.1:5000/handle_github_notification)

echo $RESPONSE
