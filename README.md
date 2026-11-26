# supplied-drops

Encrypted row drops for the supplied-documents lane (see
`supabase/migrations/20261126213000_supplied_drops_queue_v1.sql` on main).

Each `.b64` file is base64(IV + AES-256-CBC ciphertext) of rows extracted from a
manufacturer document that was supplied by hand. The database fetches the files
with pg_net and decrypts them with a key that is never committed, so the files
here are unreadable on their own.
