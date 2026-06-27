---
description: Initialize a kdbx vault + key file for an environment
argument-hint: [--env <name>]
---
Use the kdbx skill to initialize a vault and key file for this project:

    kdbx init $ARGUMENTS

It refuses to overwrite an existing vault. Afterwards, remind the user to back
up the key file out-of-band — it is the sole secret, and losing it makes the
vault unrecoverable.
