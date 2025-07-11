Quantum Piggy Farm
------------------

``qpig`` demonstrates a simple incremental game. Items in the shop are priced in
``MicroCerts`` (1/1000 of a Certainty point) which slowly recharge over time.

Veggie offers vary in price from 5 to 20 MCerts each. Feeding veggies can
temporarily double production and some veggies might grant a bonus ``QP`` when
chewed. QPellets are produced about every 30 seconds with a base 50\% chance,
modified by ±25\% depending on your Certainty. The whole interface is wrapped
in a tiny pixelated garden so outside styles don't leak in.

The farm view draws a 32x32 PNG sprite named ``pig.png`` on a canvas.
Create this image yourself (a small guinea pig with a transparent background) and
place it in this directory under ``static/games/qpig/``.

