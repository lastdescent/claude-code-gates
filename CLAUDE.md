# {{PROJECT_NAME}}

<!--
  Replace the heading and the line below with the project's name and a 1-2
  sentence description, taken from the repo's README or package manifest -
  never invented. Everything else stays as is; details live in docs/, not here.
-->

{{PROJECT_NAME}} is {{ONE-LINE DESCRIPTION OF THE PROJECT}}.

@docs/index.md

Two binding habits on every task that touches project code - the rules in
`.claude/rules/` spell them out:

1. **Read first.** The docs hub is imported above; open the detail docs it
   links for the area you are about to touch before writing code. Never guess
   at something the docs cover.
2. **Update after.** If your change alters documented behavior, update the
   owning doc in `docs/` in the same turn. A Stop hook blocks the turn until
   you do.
