-- Run this in Supabase SQL Editor before enabling commercial mode.

create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
    name text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.projects enable row level security;

drop policy if exists "Users can read their own projects" on public.projects;
drop policy if exists "Users can create their own projects" on public.projects;
drop policy if exists "Users can update their own projects" on public.projects;
drop policy if exists "Users can delete their own projects" on public.projects;

create policy "Users can read their own projects"
    on public.projects for select using (auth.uid() = owner_id);

create policy "Users can create their own projects"
    on public.projects for insert with check (auth.uid() = owner_id);

create policy "Users can update their own projects"
    on public.projects for update using (auth.uid() = owner_id);

create policy "Users can delete their own projects"
    on public.projects for delete using (auth.uid() = owner_id);

create index if not exists projects_owner_updated_idx on public.projects(owner_id, updated_at desc);
