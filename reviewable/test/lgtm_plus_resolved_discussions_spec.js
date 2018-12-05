'use strict'
/*global describe beforeEach it:true*/
const expect = require('chai').expect
const fs = require('fs')
const _ = require('underscore')

const codeToTest = fs.readFileSync('lgtm_plus_resolved_discussions.js', {encoding: 'utf8'})
const funcToTest = new Function('_', 'review', codeToTest)

// TODO: split all tests in smaller unit tests rather of a scenario.

// This template gives the structure of the review object that is available in the
// scope when executed on reviewable. It is defined for convenient re-use in the tests below.
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

describe('Approval via LGTM', () => {
  let review

  beforeEach(() => {
    // Deep copy:
    review = JSON.parse(JSON.stringify(template))
  })

  it('should not be complete without LGTM of one assignee', () => {
    review.pullRequest.assignees.push({username: 'pcorpet'})
    let res = funcToTest(_, review)
    expect(res.completed).to.equal(false)

    review.sentiments.push({
      username: 'dedan',
      emojis: ['blablabla'],
    })
    res = funcToTest(_, review)
    expect(res.completed).to.equal(false)

    review.sentiments.push({
      username: 'pcorpet',
      emojis: ['blablabla'],
    })
    res = funcToTest(_, review)
    expect(res.completed).to.equal(false)

    review.sentiments.push({
      username: 'pcorpet',
      emojis: ['lgtm'],
    })
    res = funcToTest(_, review)
    expect(res.completed).to.equal(true)
  })
})


describe('Approval', () => {
  let review

  beforeEach(() => {
    // Deep copy:
    review = JSON.parse(JSON.stringify(template))
  })

  it('marks discussions as unresolved when someone is blocking, even with an LGTM', () => {
    review.pullRequest.assignees.push({username: 'pcorpet'})
    review.sentiments.push({
      username: 'pcorpet',
      emojis: ['lgtm'],
    })
    review.discussions.push({
      numMessages: 2,
      resolved: false,
      participants: [
        {
          username: 'testbayes',
          resolved: false,
          disposition: 'blocking',
        },
        {
          username: 'dedan',
          resolved: false,
          disposition: 'following',
        },
      ],
    })
    const res = funcToTest(_, review)
    expect(res.debug.allDiscussionsResolved).to.equal(false)
    expect(res.completed).to.equal(false)
    expect(res.description).to.include('Unresolved discussions')
  })

  it('marks discussions as resolved when the author is satisfied', () => {
    review.pullRequest.author.username = 'dedan'
    review.pullRequest.assignees.push({username: 'pcorpet'})
    review.sentiments.push({
      username: 'pcorpet',
      emojis: ['lgtm'],
    })
    review.discussions.push({
      numMessages: 2,
      resolved: false,
      participants: [
        {
          username: 'testbayes',
          resolved: false,
          disposition: 'blocking',
        },
        {
          username: 'dedan',
          resolved: true,
          disposition: 'satisfied',
        },
      ],
    })
    const res = funcToTest(_, review)
    expect(res.debug.allDiscussionsResolved).to.equal(true)
    expect(res.completed).to.equal(true)
  })

  it('describes the line with a discussion that is not complete', () => {
    review.pullRequest.assignees.push({username: 'pcorpet'})
    review.sentiments.push({
      username: 'pcorpet',
      emojis: ['lgtm'],
    })
    review.discussions.push({
      numMessages: 2,
      resolved: false,
      participants: [
        {
          username: 'testbayes',
          resolved: false,
          disposition: 'blocking',
        },
        {
          username: 'dedan',
          resolved: false,
          disposition: 'following',
        },
      ],
      target: {
        file: 'frontend/server/diagnostic.py',
        line: 88,
        revision: 'r1',
      },
    })
    const res = funcToTest(_, review)
    expect(res.debug.allDiscussionsResolved).to.equal(false)
    expect(res.completed).to.equal(false)
    expect(res.description).to.include('Unresolved discussions')
    expect(res.description).to.include('frontend/server/diagnostic.py:r1 line 88')
  })

  it('is not given when the author is the one who gave themself an LGTM', () => {
    review.pullRequest.author.username = 'dedan'
    review.pullRequest.assignees.push({username: 'dedan'})
    review.sentiments.push({
      username: 'dedan',
      emojis: ['lgtm'],
    })
    review.discussions.push({
      numMessages: 2,
      resolved: false,
      participants: [
        {
          username: 'testbayes',
          resolved: false,
          disposition: 'blocking',
        },
        {
          username: 'dedan',
          resolved: true,
          disposition: 'satisfied',
        },
      ],
    })
    const res = funcToTest(_, review)
    expect(res.completed).to.equal(false)
    expect(res.debug.allDiscussionsResolved).to.equal(true)
    expect(res.debug.atLeastOneLgtm).to.equal(false)
  })
})
