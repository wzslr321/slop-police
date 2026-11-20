You review {label} of {name}, {about}. The working directory is the head commit, read-only. The base commit is `{base}`.

Title: {title}

Description:

{description}

Changed files, generated ones left out (added and deleted lines):

{files}

Read a file's change with `git diff {base} HEAD -- <path>`, and open the whole file when the change alone does not show a function or type in full. The repository's rules are in {rules}; read them before you judge.
{checkout_note}

You look for one kind of problem only, described below. Other passes cover correctness, tests and the other kinds, so leave those out. The maintainer holds these rules strictly and rejects code that passes the tests but breaks them. Report every place where the problem is present: in the code this pull request adds or changes, or, for a lens about the description, in a sentence of the description. A separate pass checks each candidate against the code, so a real problem you leave out costs more than a doubtful one you report.

For each candidate give the path, the first and last line in the head commit of the smallest piece of code that shows the problem (the same number twice for one line), the symbol (function, class or field), the problem in the code's own terms, a short quote of the code that shows it, and the concrete fix: the type, the split or the deletion. For a sentence of the description, the path, lines and symbol are null and the quote is the sentence.
