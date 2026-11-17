# Deliverable: 01-rescan

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `inventory.json` and `inventory.md`, exactly as `tools/scan.py` wrote them.
- `rescan-notes.md`.

## Format

`rescan-notes.md` sections: Command (as run, no values); Choices (vault listing yes or no, asked again this time; projects; extra files); Baseline (the path of the last inventory); Needs a look (sources with status malformed, unreadable, too-large or error); New from the person (a table: Item, Group, Where it lives, How they sign in, Work or personal); Stopped using; Rotation asked for.

## Must be true

- The inventory files are the scanner's own output, not edited.
- The vault listing question was asked again, and the answer is recorded.
- Every item the person named is recorded in their words, with "I don't know" where they did not know.
- No value appears anywhere.

## Out of scope

- Comparing with the baseline. That is `02-diff`.
- Changing anything.
