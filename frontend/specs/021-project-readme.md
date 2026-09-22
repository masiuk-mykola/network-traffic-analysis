# 021 — The project README

## Context

The task's closing section says what to send: a repository with its history, a README saying how to
run it, what is done, what is not and why, at least one test to point at, and — if AI was used —
where, and what was fixed by hand. It also asks, in as many words, that anything in the API that
looks broken be said out loud, because that is part of the job.

The README today holds only the investigation from the previous step. Everything else a reader needs
is scattered: how to start the API and the app, what the three screens do, which parts of the plan
were finished and which were deliberately left, and the defects found along the way — two in the
backend as it was handed over, one in the API's own document, and one in this app that is currently
written down rather than fixed.

A reader of this repository is a reviewer with an hour, not a colleague with a week. They need to
run it, see that it works, know what to trust, and know what the author knows about its edges.

## Goals / Non-goals

**Goals**

- A reader can run the app and the API from a cold checkout by following the file, without guessing.
- What is built is described in a paragraph a reviewer can hold in their head, not a tour of folders.
- What is not built is listed with the reason, including the parts deliberately skipped.
- The tests are pointed at: what kinds exist, what each proves, and the single command for each.
- The defects found in the given backend and in its published contract are stated plainly.
- The use of AI in producing this work is described honestly, including what was corrected by hand.

**Non-goals**

- A tutorial for the stack, a component catalogue, or documentation of every module.
- Marketing tone, screenshots, or a roadmap of imagined future work.
- Repeating the investigation, which already has its own section.
- Changing any behaviour: this step writes, it does not fix.

## Requirements

- The file opens with what this is and what it talks to, in two or three sentences.
- It gives the shortest path to a running system — the API first, then the app — with the commands
  in the order someone actually types them, and says what is needed beforehand.
- It states what each of the three screens does, and what the app deliberately does not do.
- It describes the shape of the thing in a paragraph: where the token lives, what the browser is
  allowed to talk to, and why it is arranged that way.
- It says which parts of the plan are finished and which are not, and for each unfinished part, why —
  including the ones dropped on purpose rather than for lack of time.
- It names the tests: how many and of what kind, what they are aimed at, the command for each, and
  the one that verifies this client against the server's own rules rather than against itself.
- It reports the problems found in what was given: the two that stopped the backend from starting as
  shipped, and the places where the API's document and the API's behaviour disagree.
- It states where AI was used in building this, and what a human corrected, without overstating
  either.
- Nothing in it is a claim the reader cannot check by running a command or opening a file in the
  repository.

## Acceptance criteria

1. A reader who follows the file from a clean checkout gets a running app against a running API —
   current: NO → expected: YES.
2. The file says what is done and what is not, with a reason for each omission — current: NO →
   expected: YES.
3. It points at the tests, with the command for each kind and what each kind proves — current: NO →
   expected: YES.
4. It names the defects found in the given backend and in its published contract — current: NO →
   expected: YES.
5. It says where AI was used and what was corrected by hand — current: NO → expected: YES.
6. Every command in it works as written, from the repository as it stands — current: NO → expected:
   YES.
7. The investigation section from the previous step is still there and still correct — current: YES →
   expected: YES (must not regress).

## Open questions

- What to say about the human's own contribution. The work was produced through an AI agent under a
  person's direction, and only that person can state truthfully what they corrected, rejected or
  decided. Proposed: the file states the process and the decisions taken; the sentence about what was
  fixed by hand is written by the author before sending.
- Whether the known defect in this app's estimate is reported as a limitation or fixed first.
  Proposed: decide in the next step; if it is fixed, the note becomes a line in what was fixed rather
  than in what is known-broken.
