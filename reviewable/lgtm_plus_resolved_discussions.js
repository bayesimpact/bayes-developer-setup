'use strict'
// This code will check that the pull request has been approved
// via LGTM (Looks Good To Me) emojis by at least one assignee.
// Additionally the PR author has to answer all discussions.

// When run on reviewable, this script will have a `review` object
// accessible in its scope. This object contains all the information
// about the current PR.

/*global _ review:true*/

const descriptions = []

// LGTM approval.
// TODO: Check for LGTM cancellation.
// Approval by username
const approvals = []
_.each(review.sentiments, function(sentiment) {
  const emojis = _.indexBy(sentiment.emojis)
  if (emojis.lgtm || emojis.lgtm_strong) {
    approvals.push(sentiment.username)
  }
})

const assignees = _.pluck(review.pullRequest.assignees, 'username')
const atLeastOneLgtm = !!_.intersection(approvals, assignees).length
if (!atLeastOneLgtm) {
  descriptions.push('LGTM missing')
}


// Discussion resolved approval.
const author = review.pullRequest.author.username
const discussionsBlockedByAuthor = _.chain(review.discussions).
    pluck('participants').
    flatten().
    where({resolved: false, username: author, disposition: 'discussing'}).
    value()
const allDiscussionsResolved = !discussionsBlockedByAuthor.length
if (!allDiscussionsResolved) {
  descriptions.push('Unresolved discussions')
}


// Output
const description = descriptions.join(', ')
const shortDescription = description

return {
  completed: atLeastOneLgtm && allDiscussionsResolved,
  pendingReviewers: [],
  description,
  shortDescription,
  debug: {atLeastOneLgtm, allDiscussionsResolved},
}
