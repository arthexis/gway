Recipe file features
====================

Overview
--------
GWAY recipe files (``.gwr``) let you run scripted Gateway commands with ``gway -r`` or ``gw.run_recipe``. The loader accepts ``.gwr``, ``.md``, and ``.txt`` files and tries helpful name variants (such as swapping dashes, underscores, or dots) when looking in the bundled ``recipes/`` directory. If you point to a non-existent path, it raises a clear error unless you explicitly opt into non-strict resolution.

Command chaining helpers
------------------------
Recipes support concise, multi-line commands. Ending a line with ``:`` or placing a colon after a flag records the shared prefix so later lines can append options without repetition. Indented lines that start with ``--`` reuse the previous command prefix, and a trailing ``\\`` continues a line onto the next row. Inline ``#`` comments are preserved alongside the command for later display.

Markdown-aware parsing
----------------------
You can paste Markdown into recipe files. The loader strips list markers, blockquotes, emphasis markers, and inline code wrappers. If a recipe contains fenced code blocks (````` or ``~~~``), only the code blocks are considered executable: any text outside those fences is ignored. Anonymous blocks or ones labeled ``gway`` run through the normal recipe parser, while ``python`` blocks are executed directly via ``exec`` (optionally returning a ``result`` variable). Other languages are rejected with an error for now. When a file has no fenced blocks, every normalized line is treated as part of the recipe.

Sections and comments
---------------------
Any line beginning with ``#`` becomes a comment entry that prints during recipe execution. A single leading ``#`` also defines a section header; the ``--section`` flag (or ``section=`` in ``gw.run_recipe``) filters execution to that header and the commands beneath it. Comments are stored with their section so you get readable annotations when running the recipe.

Context and templating
----------------------
Recipe comments and commands can include Gateway sigils that resolve against the current result context before printing, enabling lightweight templating for status output. You can also provide extra context values via ``--key value`` arguments when launching a recipe; those values merge into the runtime context for command execution.

Ad-hoc scripts
--------------
If you call ``gw.run`` with lines that are not stored in a recipe file, Gateway writes an ad-hoc ``.gwr`` script to the ``work`` directory (including metadata about the call) and executes it as a normal recipe.
