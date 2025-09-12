Changelog
=========

Unreleased
----------

- ensure ``gway.builtins`` package is included in distribution

0.4.59 [build 27aace]
---------------------

- 4fb1f00 Store VIN and validator; add weekly RFID report

0.4.58 [build f9604d]
---------------------

- c5a8a3c Add release tagging and workflow

0.4.57 [build 61b433]
---------------------

- web app now fetches release dates from PyPI per version
- footer handling moved to new ``web.footer`` project and recipes updated

0.4.56 [build e6cbf4]
---------------------

- 70f25f8 Remove failing cp simulator test

0.4.55 [build 429e64]
---------------------

- 73aa45b Improve CP simulator status tracking

0.4.54 [build a79b2b]
---------------------

- 4b19dce feat: watch until for future async tasks

0.4.53 [build def537]
---------------------

- 4f53731 fix website

0.4.52 [build d4b3c2]
---------------------

- f4b70e2 Add CP simulator start test

- add --install option to test command
- allow backslash line continuations in recipe files
- fix missing ``/ocpp/csms`` route for charger details
- add ``--full`` flag to ``web.app.setup_app`` to auto-load sub-projects
  and resolve sub-project views without wrappers

0.4.51 [build edbd5b]
---------------------

- ba12c56 fix: run upgrade script via bash

0.4.50 [build a319ee]
---------------------

- 8fed401 Track last heartbeat and format update times

0.4.49 [build 339f37]
---------------------

- d154615 Add flexible SQL model helper

0.4.48 [build be6089]
---------------------

- 970ec5d Remove init-root command and tests

0.4.47 [build 32d6a9]
---------------------

- d2bde7a qpig.css renamed and tweaked

0.4.46 [build 6c1819]
---------------------

- 843e8f8 Ensure glitch-punk background stays dark

0.4.45 [build 22d8d2]
---------------------

- b56c0dd cleanup intents

0.4.44 [build 640ce4]
---------------------

- 7ee813d Use gw.cast helpers in web

0.4.43 [build cf2bd4]
---------------------

- da736a6 fix missing setup-app for csms

- support gw-on-load for one-time refresh events in render.js
- add ChatGPT actions with passphrase trust system (web.chat.actions)
- add audit log page for chat actions (view_audit_chatlog)
 
0.4.42 [build 68c493]
---------------------

- 2dee342 fix classic-95 text input styling

- Add **Random** option to the style switcher drop-down and support
  saving it in the ``css`` cookie.

0.4.41 [build 4a9512]
---------------------

- e31f6a4 install openpyxl

- Allow spaces in kwarg values for CLI and recipes

0.4.40 [build 225d99]
---------------------

- 0b416ec fix ocpp.data to load directly
- Allow specifying service user and password for Windows installer
- Windows service runs `python -m gway` instead of `gway.bat`

0.4.39 [build ccb94e]
---------------------

- b17445d Fix Windows service start
- Rework nmcli monitor to report status only and provide a web command interface

- Ensure nmcli hotspot sets IPv4 address via AP_GATEWAY or default 10.42.0.1

0.4.38 [build 425327]
---------------------

- a4056e5 Improve nmcli monitor table styling
- Ignore "service has not been started" error when removing Windows services

0.4.37 [build 6aa9b9]
---------------------

- 633461d start Windows service after installation

0.4.36 [build 4c763d]
---------------------

- 9bbd954 Make upgrade script resilient offline

0.4.35 [build d4bb5d]
---------------------

- ca795a3 fix service install script

0.4.34 [build 673405]
---------------------

- 6e2494d PyPI Release v0.4.33

0.4.33 [build e7a1df]
---------------------

- Fix changelog to skip merge commits


0.4.32 [build 51ffc92]
----------------------

- 441cae2 Applying previous commit.
- 51ffc92 PyPI Release v0.4.32
- dc61022 fix build
- 844a692 Set default mask for parse_log
- 231f540 Add per-project coverage reporting
- f71afe8 fix gamebox recipe
- 06a5406 Remove unwrap helpers and switch to match
- bc5a52f fix: clear registered routes when creating new app
- 8a534d2 Expand project summary in AGENTS
- bd53e14 Add gamebox recipe and remove qpig from website
- 3cca0f8 Remove TODO issues summary
- d805692 Add SnL shared snakes and ladders game
- d445d55 style(nav): compact home links
- 2043b1a Add web URL tests
- e3c073a Add tests for web app utilities
- 3163d4d Add cookie utility tests
- b3960c8 Fix Unicode search fallback
- cd64d33 Add unit tests for site filename helpers
- ba5b4c7 Add changelog tracking and view
- f176ed3 fix windows service install args

0.4.31 [build 937abe0]
----------------------

- Initial CHANGELOG created.

