## Lens: code that is hard to read

The package is small on purpose. A reader should follow any function from its name and body, without tracing the rest of the package or running it in their head.

Report, in the Python and the action files the change adds or grows:

- A function that does several things in a row where named steps would read better, or one that a reader cannot take in at a glance.
- Decisions nested more than two levels deep, or a condition that needs a pause to evaluate.
- A value with meaning that travels as a raw `dict`, `str` or tuple where a small dataclass or an `Enum` would name it.
- A name that says less than the value holds, or something else.
- Shell in an action file that decides something, where Python and its tests should.

For each, say what a reader has to hold in mind and the fix: the steps and their names, the type, the early return. Leave out code that is long but plain, and style a formatter would settle.
