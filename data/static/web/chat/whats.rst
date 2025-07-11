WhatsApp Integration
--------------------

The ``web.chat.whats`` module provides helpers to send text messages using the
`WhatsApp Cloud API <https://developers.facebook.com/docs/whatsapp>`_.

Example::

    gw.web.chat.whats.send_message("+15551234567", "Hello from GWAY")

Set ``WHATS_TOKEN`` and ``WHATS_PHONE_ID`` environment variables with your
Cloud API credentials. The ``api_post_send`` endpoint can be invoked via
``/api/web/chat/whats/send`` once the web server is running.
