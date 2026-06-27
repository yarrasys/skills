---
description: Run a command with this project's secrets injected from the kdbx vault (never printed)
argument-hint: <command> [args...]
---
Use the kdbx skill to run the following command with the active environment's
mapped secrets injected into its process environment, **without printing any
secret value**:

    kdbx run -- $ARGUMENTS

Report the command's output. Never reveal, echo, or log a secret value.
