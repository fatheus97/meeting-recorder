# Open items ledger

SYNTHETIC EXAMPLE: every person, project and date here is invented. The user is Alice
(`board.py --me Alice`); Bob builds, Carol runs finance, Dave designs, Erin runs ops.
Format: see `../LEDGER.md`. `[ ]` open, `[~]` changed, `[x]` closed. IDs never reused.

<!-- next-id: 16 -->

## website

- [ ] `OI-1` #website #handover Contact form posts to the new mail provider; the old relay stays as fallback until launch — **Alice** — me — seen 2025-03-03 [00:04:12]
  ↳ [3.3] Head was: "Pick a mail provider for the contact form". Bob picked one at the sync; wiring it is Alice's.
- [ ] `OI-2` #website #org Cookie banner copy needs a legal read before launch — **Dave** — waiting on Erin — seen 2025-03-03 [00:11:50]
- [~] `OI-3` #website Launch moved to the week of 17 March; staging is green — **Bob** — — — seen 2025-03-10 [00:02:31]
  ↳ [10.3] Head was: "Launch on 10 March". Moved at the sync, nobody objected.
- [ ] `OI-4` #website #billing Pricing page still shows last year's tax note
- [ ] `OI-8` #website New product photos for the landing page — **Alice** — seen 2025-03-03 [00:08:02]
  ↳ [6.3] Dave has the shoot booked for Thursday — waiting on Dave
- [x] `OI-9` #website Staging environment for the redesign — **Bob** — seen 2025-02-24 [00:15:30] ✅ **[6.3]** done, Bob shared the URL

### Threats

- [ ] `OI-11` #website #org Nobody owns the domain renewal; the registrar account is in a former contractor's name — **UNOWNED** — — — seen 2025-03-03 [00:31:02]

## billing

- [ ] `OI-5` #billing Invoice numbering restarts every January; the accountant wants one continuous series — **Carol** — seen 2025-03-03 [00:19:05]
  ↳ [5.3] Alice: waiting on Carol — she is checking with the auditor
  ↳ [4.3] Carol: the auditor accepts either format, the question is only which one we keep
- [ ] `OI-7` #billing Quarterly revenue export for the accountant, owned by **Carol** — seen 2025-03-03 [00:21:44]

### Preconditions

- [ ] `OI-12` #billing #website Online payments go live only after the new invoice template is approved — **Carol** — waiting on Bob — seen 2025-03-10 [00:09:14]

## org

- [ ] `OI-6` #org #billing Expense policy draft: who approves travel above the limit is not decided
  — **Erin** (drafting) — seen 2025-03-04 [00:27:10]
- [~] `OI-10` #org Team offsite: venue booked ⚠ **[7.3]** the date clashes with the billing freeze, needs a new one
- [ ] `OI-15` #org #handover Write down how the release checklist works before Alice's leave in June — **Alice** — me — seen 2025-03-10 [00:40:05]
- [x] `OI-13` #org Weekly sync moves to Tuesdays — **Alice** — — — seen 2025-02-24 [00:01:10]
  ↳ [3.3] done

## Unsorted

<!-- OI-14 is deliberately untagged to fill the board's "no project" bucket; LEDGER.md has a check that flags these. -->
- [ ] `OI-14` Find out whether the old analytics account can be closed
