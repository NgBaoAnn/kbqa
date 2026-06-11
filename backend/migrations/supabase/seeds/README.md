# Supabase Manual Test Seeds

Create these users in Supabase Auth first, then run
`202606110002_manual_test_seed.sql` in the Supabase SQL Editor.

Suggested accounts:

| Email | Purpose |
|---|---|
| `manual.user@example.com` | Normal active user with seeded conversation/messages |
| `manual.other@example.com` | Different owner for authorization isolation tests |
| `manual.admin@example.com` | Admin profile for admin dependency tests |
| `manual.inactive@example.com` | Inactive profile for protected API denial tests |

Use any password you want when creating the Auth users. The backend still uses
real Supabase access tokens; this seed only creates app-data rows tied to those
Auth users.

After running the seed, sign in through Supabase Auth to get an access token for
each account and use the manual-test curl commands against the backend.
