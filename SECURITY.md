# Security notes

LinguaDesk is designed to support privacy-sensitive translation workflows, but deployment configuration remains important.

- Keep Supabase publishable/anon keys in Streamlit Secrets, never in source control.
- Never place a Supabase secret/service-role key in the app.
- Use Local-only mode for material that cannot leave the approved environment.
- Run `supabase_schema.sql` and keep Row Level Security enabled.
- Configure Supabase email confirmation and password recovery URLs for the deployed app.
- Add a retention and deletion policy before accepting regulated client data.
- Use private hosting for confidential or regulated projects.

The application is not a substitute for an institutional security review, a data-processing agreement, or legal advice.
