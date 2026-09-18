# TODO – Admin Dashboard User Row Rules

Release Manager manual verification steps for the new admin dashboard row rule checks:

1. Log into the admin dashboard with superuser credentials.
2. Navigate to the **User** model listing and ensure the row rule banner reports green status.
3. Edit the built-in `admin` account and assign it a Watchtower role (or equivalent group), leaving the user active. Confirm the dashboard flags the violation and that deactivating the account clears the alert.
4. Inspect the list of superusers and ensure at least one has a populated email address. Add an email to a superuser and confirm the dashboard reflects the compliance state.
5. Revert any test role or email changes made during verification.
