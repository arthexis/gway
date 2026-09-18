Unified Authentication Database
-------------------------------

``projects/auth_db`` provides a small helper that stores authentication
information in a DuckDB database. Multiple login methods can be linked
via a shared ``identity_id``.

The tables are created automatically using ``gw.sql.model`` the first time
any helper function is called.  By default the database is stored in
``work/auth.duckdb`` but all functions accept a custom ``dbfile``
parameter for testing or advanced setups.

Available helpers include:

``create_identity`` – add a new identity and return its id.

``set_basic_auth`` – store HTTP Basic credentials for an identity.

``verify_basic`` – validate a username/password pair.
