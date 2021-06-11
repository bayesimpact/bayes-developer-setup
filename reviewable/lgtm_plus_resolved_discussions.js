'use strict'
// This code will check that the pull request has been approved
// via LGTM (Looks Good To Me) emojis by at least one assignee or requested
// reviewer.
// Additionally the PR author has to answer all discussions.

// When run on reviewable, this script will have a `review` object
// accessible in its scope. This object contains all the information
// about the current PR.

/*global _ review:true*/

const descriptions = []

// LGTM approval.
// Approval by username
const approvals = []
_.each(_.sortBy(review.sentiments, 'timestamp'), function(sentiment) {
  const emojis = _.indexBy(sentiment.emojis)
  if (emojis.lgtm || emojis.lgtm_strong) {
    approvals.push(sentiment.username)
  }
  if (emojis.lgtm_cancel) {
    _.pull(approvals, sentiment.username)
  }
})

const author = review.pullRequest.author.username

const reviewers = _.without(
  _.union(
    _.map(review.pullRequest.requestedReviewers, 'username'),
    Object.keys(review.pullRequest.approvals || {}).
      filter(u => review.pullRequest.approvals[u] === 'approved')
  ), author)
const atLeastOneLgtm = !!_.intersection(approvals, reviewers).length
if (!reviewers.length) {
  descriptions.push('Missing an assignee or a reviewer')
} else if (!atLeastOneLgtm) {
  descriptions.push('LGTM missing from one of: ' + reviewers)
}


const isAnyoneBlocking = ({participants}) =>
  !!participants.filter(({disposition}) =>
    disposition === 'blocking' || disposition === 'working'
  ).length


const isSatisfied = (who, {participants}) =>
  !!participants.filter(({disposition, username}) =>
    who === username && disposition === 'satisfied').length


// Discussion resolved approval.
const discussionsBlockedByAuthor = review.discussions.
  filter(discussion => isAnyoneBlocking(discussion) && !isSatisfied(author, discussion))
const allDiscussionsResolved = !discussionsBlockedByAuthor.length
if (!allDiscussionsResolved) {
  const {target: {file, line, revision} = {}} = discussionsBlockedByAuthor[0]
  const example = file ? ` (${file}:${revision} line ${line})` : ''
  descriptions.push(`Unresolved discussions${example}`)
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
