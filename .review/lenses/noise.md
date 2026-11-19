## Lens: comments, docs and tests that add nothing

The code should explain itself. Text that repeats what the code or the folder tree already shows costs every reader time and goes stale first.

Report, in what the change adds:

- A comment or docstring that restates the name, the signature or the next lines.
- A README sentence that describes the code instead of what a user needs to run it, or that repeats another section.
- A test that restates the implementation, or several tests of one behaviour.
- A test fixture larger than the behaviour it sets up.

Keep a comment that says why the code is as it is when the code cannot say it, and a README sentence a user needs before the first run.
