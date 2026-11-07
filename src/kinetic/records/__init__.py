"""records (supporting, thin): clinical records about a client.

Language: Clinical Record, Record Category, Author. Records are append-only: written,
never edited or deleted. Every read and write asks access, which decides from the
record's category and author and the reader's place on the client's care team.
"""
