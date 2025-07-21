GPT Actions
-----------

``web.chat.actions`` exposes endpoints for invoking GWAY functions via ChatGPT Actions.
Authentication uses a short passphrase printed to the server console. Submit the phrase
with your first request to trust the session.

The ``GPT Actions`` home page lists available utilities in a card layout. The Audit
Chatlog can be reached via the dedicated card.

Registering the endpoint
------------------------

1. Start the web server with the actions module enabled::

       gway web.app setup-app web.chat.action --home gpt-actions

2. Open ``/api/web/chat/action/manifest`` and copy the URL.
3. In ChatGPT choose **Import from URL** and paste the manifest address.
4. Send authenticated POST requests to ``/api/web/chat/action/action``. Your first
   call will print a passphrase in the server log—repeat the request with that
   value in the ``trust`` field to run any action.

An audit log of all API messages can still be viewed at ``/web/chat/audit-chatlog``.
