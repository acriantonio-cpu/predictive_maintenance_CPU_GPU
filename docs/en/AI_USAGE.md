# Use of generative AI

> English copy of [`AI_USAGE.md`](../../AI_USAGE.md) (Italian); keep them in sync.

Declaration required by the NLnet policy on generative AI (requirement 15.8).

## What was generated with AI

The initial implementation (version 0.1.0.dev0: code in `src/`, tests in `tests/`, schemas,
workflows and documentation) was written with the assistance of **Claude Code** (Anthropic),
starting from the project specification "HWDrift — Project specification and implementation plan"
(30 September 2026). The graphical interface, the restart handling and the English localization
(GUI, reports, alarms, documentation) were added in later sessions with the same tool.

- **Summary prompts**: "implement the tool described in the attached specification to do
  predictive maintenance on local PCs; keep the documentation up to date with a document that
  explains step by step how it works and how to start it; at the end audit the code"; "what happens
  when I switch the PC off and on, add an exe with a GUI with real-time charts, configuration and
  logs"; "translate the GUI into English, create an English copy of the documentation".
- **Model**: indicated in the commit metadata (`Co-Authored-By` and `Claude-Session` lines), as
  the policy requires for traceability.

## What remains a human responsibility

The policy provides that purely generated work is not payable and that whoever develops must be
able to explain every choice. Before considering the code "one's own", the maintainer must:

1. review every module and the choices documented in `docs/en/methodology.md` (in particular §5
   "long-term σ" and §9 "departures from the specification");
2. run M0 on real hardware and fix the `TODO(M0)`;
3. answer the reviewers' questions on design and code in person;
4. have the English texts (translation catalog `src/hwdrift/i18n_en.py`, documentation)
   proofread by a fluent speaker.

## Rules for future contributions

Every commit with AI-generated or heavily AI-assisted code carries in its message:

```
AI-Assisted: <tool> <model/version>
AI-Prompt: <one-line summary of the prompt>
```

and the contributor declares having read, understood and verified the code.
