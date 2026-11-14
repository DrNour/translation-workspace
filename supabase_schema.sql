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

insert into storage.buckets (id, name, public)
values ('project-files', 'project-files', false)
on conflict (id) do nothing;

drop policy if exists "Authenticated users can upload project files" on storage.objects;
create policy "Authenticated users can upload project files" on storage.objects
    for insert to authenticated
    with check (bucket_id = 'project-files');

drop policy if exists "Authenticated users can read project files" on storage.objects;
create policy "Authenticated users can read project files" on storage.objects
    for select to authenticated
    using (bucket_id = 'project-files');

drop policy if exists "Authenticated users can update project files" on storage.objects;
create policy "Authenticated users can update project files" on storage.objects
    for update to authenticated
    using (bucket_id = 'project-files');

create table if not exists public.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
    created_at timestamptz not null default now()
);

create table if not exists public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('owner', 'manager', 'translator', 'reviewer', 'client')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create table if not exists public.audit_events (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references public.workspaces(id) on delete cascade,
    actor_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
    event_type text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.workspace_invitations (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    email text not null,
    role text not null check (role in ('manager', 'translator', 'reviewer', 'client')),
    status text not null default 'pending' check (status in ('pending', 'accepted', 'revoked')),
    invited_by uuid not null references auth.users(id) on delete cascade default auth.uid(),
    created_at timestamptz not null default now()
);

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.audit_events enable row level security;
alter table public.workspace_invitations enable row level security;

drop policy if exists "Workspace members can read workspaces" on public.workspaces;
create policy "Workspace members can read workspaces" on public.workspaces for select
    using (owner_id = auth.uid() or exists (select 1 from public.workspace_members m where m.workspace_id = id and m.user_id = auth.uid()));

drop policy if exists "Workspace owners can create workspaces" on public.workspaces;
create policy "Workspace owners can create workspaces" on public.workspaces for insert with check (owner_id = auth.uid());

drop policy if exists "Members can read membership" on public.workspace_members;
create policy "Members can read membership" on public.workspace_members for select using (user_id = auth.uid());

drop policy if exists "Workspace owners can add membership" on public.workspace_members;
create policy "Workspace owners can add membership" on public.workspace_members for insert
    with check (exists (select 1 from public.workspaces w where w.id = workspace_id and w.owner_id = auth.uid()));

drop policy if exists "Workspace owners can manage invitations" on public.workspace_invitations;
create policy "Workspace owners can manage invitations" on public.workspace_invitations for all
    using (exists (select 1 from public.workspaces w where w.id = workspace_id and w.owner_id = auth.uid()))
    with check (exists (select 1 from public.workspaces w where w.id = workspace_id and w.owner_id = auth.uid()));

drop policy if exists "Members can read audit events" on public.audit_events;
create policy "Members can read audit events" on public.audit_events for select using (actor_id = auth.uid());
