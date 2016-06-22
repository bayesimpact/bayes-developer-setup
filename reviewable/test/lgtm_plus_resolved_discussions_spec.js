'use strict'
/*global describe beforeEach it:true*/
const expect = require('chai').expect
const fs = require('fs')
const _ = require('underscore')

const codeToTest = fs.readFileSync('lgtm_plus_resolved_discussions.js', {encoding: 'utf8'})
const funcToTest = new Function('_', 'review', codeToTest)


const template = {
  summary: {},
  pullRequest: {
    author: {
      username: 'dedan',
    },
    assignees: [],
  },
  sentiments: [],
  discussions: [],
}

describe('Approval via LGTM', function() {
  let review

  beforeEach(function() {
    review = Object.assign({}, template)
  })

  it('should not be complete without LGTM of one assignee', function() {
    review.pullRequest.assignees.push({username: 'pcorpet'})
    let res = funcToTest(_, review)
    expect(res.completed).to.equal(false)

    review.sentiments.push({
      'username': 'dedan',
      'emojis': ['blablabla'],
    })
    res = funcToTest(_, review)
    expect(res.completed).to.equal(false)

    review.sentiments.push({
      'username': 'pcorpet',
      'emojis': ['blablabla'],
    })
    res = funcToTest(_, review)
    expect(res.completed).to.equal(false)

    review.sentiments.push({
      'username': 'pcorpet',
      'emojis': ['lgtm'],
    })
    res = funcToTest(_, review)
    expect(res.completed).to.equal(true)
  })
})


describe('Approval', function() {
  let review

  beforeEach(function() {
    review = Object.assign({}, template)
  })

  it('mark discussions as resolved when the author is resolved', function() {
    review.discussions.push({
      'numMessages': 2,
      'resolved': false,
      'participants': [
        {
          'username': 'testbayes',
          'resolved': false,
          'disposition': 'discussing',
        },
        {
          'username': 'dedan',
          'resolved': false,
          'disposition': 'discussing',
        },
      ],
    })
    let res = funcToTest(_, review)
    expect(res.debug.allDiscussionsResolved).to.equal(false)
    review.discussions[0].participants[1].resolved = true
    res = funcToTest(_, review)
    expect(res.debug.allDiscussionsResolved).to.equal(true)
  })
})
