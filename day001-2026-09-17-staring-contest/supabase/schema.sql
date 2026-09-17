-- Supabase SQL Editor에 붙여넣고 실행하세요.

create table if not exists public.scores (
  id bigint generated always as identity primary key,
  nickname text not null check (char_length(btrim(nickname)) between 1 and 12),
  time_ms integer not null check (time_ms between 1000 and 3600000), -- 1초 ~ 1시간
  created_at timestamptz not null default now()
);

create index if not exists scores_nickname_time_idx on public.scores (nickname, time_ms desc);

-- 로그인 없이 누구나 조회/등록만 가능 (수정·삭제 불가)
alter table public.scores enable row level security;

drop policy if exists "anyone can read scores" on public.scores;
create policy "anyone can read scores" on public.scores
  for select to anon, authenticated using (true);

drop policy if exists "anyone can insert scores" on public.scores;
create policy "anyone can insert scores" on public.scores
  for insert to anon, authenticated with check (true);

-- 닉네임별 최고 기록
create or replace view public.leaderboard
with (security_invoker = true) as
select distinct on (nickname) nickname, time_ms, created_at
from public.scores
order by nickname, time_ms desc, created_at asc;

grant select, insert on public.scores to anon, authenticated;
grant select on public.leaderboard to anon, authenticated;
