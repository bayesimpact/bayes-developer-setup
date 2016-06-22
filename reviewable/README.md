# Reviewable Configuration

We realized that the default settings of when a PR is accepted on reviewable.io is not suitable for our workflow. On reviewable you can merge a PR after all discussions are resolved, but we want it to additionally wait until at least one of the assignees gave official approval. Luckily reviewable allows the implementation of custom rules, this folder contains such a custom rule and its tests.

You can change the rules of reviewable by navigating to an open PR. Click on the `checks` circle on the top of the page. Click on the *gear symbol* to configure the acceptance rules.
