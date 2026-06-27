---
description: Store a secret in the kdbx vault (value provided by the human, never via the model)
argument-hint: <entry-path>
---
The user wants to store a secret at `$ARGUMENTS`.

🔑 **Do NOT ask the user to paste the secret into the chat**, and never place a
secret value on the command line or anywhere in this transcript. Your role is
the entry **path and variable name only**.

Instead, instruct the human to run, in **their own terminal**, one of:

    kdbx set $ARGUMENTS < secret.txt     # value piped from a file
    kdbx set $ARGUMENTS                  # value typed at the hidden getpass prompt

In CI, an outer orchestrator sets an env var and you pass `--from-env VAR`. See
the skill's `SKILL.md` security rules.
