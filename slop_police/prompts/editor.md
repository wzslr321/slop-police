You edit the checked review comments on {label} of {name} before they reach the maintainer. Several passes wrote them, one per kind of problem, so the same code can appear in more than one.

Comments, numbered:

{comments}

1. Merge comments about the same problem in the same code into one, keeping every concrete point and fix. Two different problems in one function stay two comments.
2. Order the result by what the maintainer would fix first. {priority}
3. Drop nothing for being small. Drop only a comment that another one fully contains.

Return the comments in that order, each with the path and line of its main place and its body. Keep the bodies short and plain: the place and symbol, what is wrong, the fix.
